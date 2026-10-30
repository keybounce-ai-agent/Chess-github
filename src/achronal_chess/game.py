from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import chess

from .config import BalanceConfig
from .economy import CostModel
from . import BoardState, Timeline, Wave, ActionLog, GameError, BoardView, Forecast  # noqa: F401

__all__ = [
    "Position",
    "legal_moves",
    "is_legal_move",
    "is_checkmate",
    "is_stalemate",
    "is_draw",
    "detect_marks",
    "BoardView",
    "Forecast",
    "Game",
]


@dataclass
class Position:
    board: chess.Board = field(default_factory=chess.Board)
    side_to_move: str | None = None
    castling: str | None = None
    en_passant: str | None = None
    halfmove_clock: int = 0
    hash: int = 0

    def __post_init__(self) -> None:
        if self.side_to_move is None:
            self.side_to_move = "white" if self.board.turn == chess.WHITE else "black"
        if self.castling is None:
            castling = ""
            if self.board.has_kingside_castling_rights(chess.WHITE):
                castling += "K"
            if self.board.has_queenside_castling_rights(chess.WHITE):
                castling += "Q"
            if self.board.has_kingside_castling_rights(chess.BLACK):
                castling += "k"
            if self.board.has_queenside_castling_rights(chess.BLACK):
                castling += "q"
            self.castling = castling
        if self.en_passant is None:
            self.en_passant = self.board.ep_square and chess.square_name(self.board.ep_square) or None
        self.hash = self.board.__hash__()  # compatibility placeholder; deterministic within process


def legal_moves(position: Position | chess.Board) -> list[chess.Move]:
    board = position.board if isinstance(position, Position) else position
    return list(board.legal_moves)


def is_legal_move(position: Position | chess.Board, move: chess.Move | str) -> bool:
    board = position.board if isinstance(position, Position) else position
    candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
    return candidate in board.legal_moves


def is_checkmate(board: chess.Board) -> bool:
    return board.is_checkmate()


def is_stalemate(board: chess.Board) -> bool:
    return board.is_stalemate()


def is_draw(board: chess.Board) -> bool:
    return board.is_insufficient_material() or board.is_seventy_five_moves() or board.is_fivefold_repetition() or board.is_repetition(3)


def detect_marks(board: chess.Board, index: int) -> list[str]:
    marks: list[str] = []
    if board.is_checkmate():
        marks.append("checkmate")
    if board.is_stalemate():
        marks.append("stalemate")
    if board.is_repetition(3):
        marks.append("threefold")
    if board.is_seventy_five_moves():
        marks.append("fifty_move")
    if board.is_insufficient_material():
        marks.append("insufficient")
    return marks


class Game:
    def __init__(self, config: BalanceConfig | None = None) -> None:
        self.config = config or BalanceConfig.default()
        self.cost_model = CostModel(self.config)
        self.timeline = Timeline()
        self.action_log = ActionLog()
        self.waves: list[Wave] = []
        self.marks: list[dict[str, Any]] = []
        self.turn_index = 0
        self.pending_actor: str | None = "white"
        self.frozen_board: int | None = None
        self.players = {
            "white": {"color": "white", "energy": self.config.start_energy["white"]},
            "black": {"color": "black", "energy": self.config.start_energy["black"]},
        }
        board = chess.Board()
        self.timeline.append_state(Position(board=board, side_to_move="white"), None)

    @property
    def current_player(self) -> str:
        return "white" if self.turn_index % 2 == 0 else "black"

    @property
    def config_hash(self) -> str:
        payload = {
            "WAVE_STEPS_PER_TURN": self.config.WAVE_STEPS_PER_TURN,
            "ENERGY_SCALE": self.config.ENERGY_SCALE,
            "regen_per_turn": self.config.regen_per_turn,
            "start_energy": self.config.start_energy,
            "max_energy": self.config.max_energy,
            "cost_per_turn_back": self.config.cost_per_turn_back,
            "transfer_pct_edit": self.config.transfer_pct_edit,
            "transfer_pct_response": self.config.transfer_pct_response,
        }
        return json.dumps(payload, sort_keys=True)

    def _state_for_index(self, index: int) -> BoardState:
        if index < 0 or index >= len(self.timeline.states):
            raise IndexError(f"State index {index} out of range")
        return self.timeline.states[index]

    def _is_own_ply(self, actor: str, index: int) -> bool:
        if index % 2 == 0:
            return actor == "white"
        return actor == "black"

    def _apply_move_to_board(self, board: chess.Board, move: chess.Move | str) -> chess.Board:
        if isinstance(move, str):
            move = chess.Move.from_uci(move)
        next_board = board.copy()
        next_board.push(move)
        return next_board

    def add_mark(self, index: int, kind: str) -> None:
        self.marks.append({"index": index, "kind": kind})

    def validate_present_move(self, actor: str, move: chess.Move | str) -> None:
        if actor != self.current_player:
            raise GameError("ERR_NOT_YOUR_TURN", f"It is {self.current_player}'s turn")
        if self.frozen_board is not None:
            raise GameError("ERR_PRESENT_MOVE_BLOCKED", "No present move while a mark exists")
        board = self.timeline.states[-1].position.board
        if isinstance(move, str):
            move = chess.Move.from_uci(move)
        if move not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Move is illegal in the present position")

    def present_move(self, actor: str, move: chess.Move | str) -> BoardState:
        self.validate_present_move(actor, move)
        board = self.timeline.states[-1].position.board
        if isinstance(move, str):
            move = chess.Move.from_uci(move)
        next_board = board.copy()
        next_board.push(move)
        state = BoardState(index=len(self.timeline.states), position=Position(board=next_board, side_to_move="white" if next_board.turn == chess.WHITE else "black"))
        self.timeline.states.append(state)
        self.action_log.append(actor, "PresentMove", None, self.config_hash)
        self.turn_index += 1
        self.pending_actor = self.current_player
        self._evaluate_marks()
        return state

    def edit_past(self, actor: str, index: int, move: chess.Move | str) -> None:
        if not self._is_own_ply(actor, index):
            raise GameError("ERR_NOT_YOUR_PLY", "Only your own plies may be edited")
        board = self.timeline.states[index].position.board
        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        if candidate not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Edit does not match the current position")
        if self.frozen_board is not None and index >= self.frozen_board:
            raise GameError("ERR_EDIT_AT_OR_AFTER_FROZEN", "Edits below the frozen board only")
        if self.players[actor]["energy"] < self.cost_model.cost(len(self.timeline.states) - 1, index):
            raise GameError("ERR_INSUFFICIENT_ENERGY", "Insufficient energy for edit")
        self.timeline.states[index].move = candidate
        self.players[actor]["energy"] -= self.cost_model.cost(len(self.timeline.states) - 1, index)
        self.action_log.append(actor, "PastEdit", None, self.config_hash)
        self.waves.append(Wave(id=len(self.waves), origin=index, front=index))

    def respond(self, actor: str, index: int, move: chess.Move | str) -> None:
        state = self.timeline.states[index]
        board = state.position.board
        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        if candidate not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Response move is illegal")
        cost = self.cost_model.cost(len(self.timeline.states) - 1, index)
        paid = min(self.players[actor]["energy"], cost)
        self.players[actor]["energy"] -= paid
        self.timeline.states[index].move = candidate
        self.action_log.append(actor, "Respond", None, self.config_hash)

    def pass_turn(self, actor: str) -> None:
        if self.frozen_board is None:
            raise GameError("ERR_PASS_NOT_ALLOWED", "Pass only in freezing conditions")
        self.action_log.append(actor, "Pass", None, self.config_hash)

    def _evaluate_marks(self) -> None:
        for i, state in enumerate(self.timeline.states):
            board = state.position.board
            marks = detect_marks(board, i)
            for kind in marks:
                self.marks.append({"index": i, "kind": kind})
        if self.marks:
            self.frozen_board = min(m["index"] for m in self.marks)

    def board_view(self, index: int) -> BoardView:
        state = self.timeline.states[index]
        return BoardView(now=state.position.board, projected=state.position.board, status="certain")

    def forecast(self) -> Forecast:
        return Forecast(positions=[state.position.board for state in self.timeline.states], eta=[0 for _ in self.timeline.states], stall_points=[None for _ in self.timeline.states])

    def legal_responses(self, index: int) -> list[chess.Move]:
        return list(self.timeline.states[index].position.board.legal_moves)

    def serialize(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "pending_actor": self.pending_actor,
            "frozen_board": self.frozen_board,
            "players": self.players,
            "timeline": [
                {
                    "index": state.index,
                    "fen": state.position.board.fen(),
                    "move": state.move.uci() if state.move is not None else None,
                }
                for state in self.timeline.states
            ],
            "marks": self.marks,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Game":
        game = cls()
        game.turn_index = payload.get("turn_index", 0)
        game.pending_actor = payload.get("pending_actor")
        game.frozen_board = payload.get("frozen_board")
        game.players = payload.get("players", game.players)
        for entry in payload.get("timeline", []):
            board = chess.Board(entry["fen"])
            move = chess.Move.from_uci(entry["move"]) if entry.get("move") else None
            game.timeline.append_state(Position(board=board, side_to_move="white" if board.turn == chess.WHITE else "black"), move)
        game.marks = payload.get("marks", [])
        return game
