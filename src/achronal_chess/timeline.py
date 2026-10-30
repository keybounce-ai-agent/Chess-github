from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import chess

from .chess_core import Position, apply_move, legal_moves, is_legal_move, detect_marks
from .config import BalanceConfig
from .economy import CostModel, apply_payment, regen_for_turn
from . import BoardState, Timeline, Wave, ActionLog, GameError, BoardView, Forecast, Player, Mark

__all__ = [
    "Game",
]


@dataclass
class Game:
    config: BalanceConfig = field(default_factory=BalanceConfig.default)
    timeline: Timeline = field(default_factory=Timeline)
    action_log: ActionLog = field(default_factory=ActionLog)
    waves: list[Wave] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    turn_index: int = 0
    pending_actor: str | None = "white"
    frozen_board: int | None = None
    players: dict[str, Player] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cost_model = CostModel(self.config)
        if not self.timeline.states:
            start_board = chess.Board()
            self.timeline.append_state(Position(board=start_board), move=None)
        if not self.players:
            self.players = {
                "white": Player(color="white", energy=self.config.start_energy["white"]),
                "black": Player(color="black", energy=self.config.start_energy["black"]),
            }
        if self.pending_actor is None:
            self.pending_actor = self.current_player

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

    def _player_owner_for_state_index(self, index: int) -> str:
        return "white" if index % 2 == 0 else "black"

    def _is_own_ply(self, actor: str, index: int) -> bool:
        owner = self._player_owner_for_state_index(index)
        return actor == owner

    def _board_at_index(self, index: int) -> chess.Board:
        return self.timeline.states[index].position.board

    def _legal_moves_for_index(self, index: int) -> list[chess.Move]:
        return legal_moves(self._board_at_index(index))

    def _evaluate_marks(self) -> None:
        marks_in_order: list[Mark] = []
        for idx, state in enumerate(self.timeline.states):
            board = state.position.board
            for kind in detect_marks(board, idx):
                marks_in_order.append(Mark(index=idx, kind=kind))
        self.marks = marks_in_order
        if self.marks:
            self.frozen_board = min(m.index for m in self.marks)
        else:
            self.frozen_board = None

    def _apply_payment(self, payer: str, recipient: str, amount: int, transfer_pct: int) -> None:
        payer_energy = self.players[payer].energy
        recipient_energy = self.players[recipient].energy
        cap = self.config.max_energy[recipient]
        payer_energy, recipient_energy, _ = apply_payment(
            payer_energy=payer_energy,
            recipient_energy=recipient_energy,
            amount=amount,
            transfer_pct=transfer_pct,
            cap=cap,
        )
        self.players[payer].energy = payer_energy
        self.players[recipient].energy = recipient_energy

    def regenerate(self, actor: str) -> None:
        if self.frozen_board is not None:
            return
        cap = self.config.max_energy[actor]
        self.players[actor].energy = regen_for_turn(self.players[actor].energy, cap, self.config.regen_per_turn)

    def validate_present_move(self, actor: str, move: chess.Move | str) -> None:
        if actor != self.current_player:
            raise GameError("ERR_NOT_YOUR_TURN", f"Expected {self.current_player}'s turn, got {actor}.")
        if self.frozen_board is not None:
            raise GameError("ERR_PRESENT_MOVE_BLOCKED", "No present move while a freeze mark exists.")

        board = self.timeline.states[-1].position.board
        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        if candidate not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Move is not legal in the current position.")

    def present_move(self, actor: str, move: chess.Move | str) -> BoardState:
        self.validate_present_move(actor, move)
        board = self.timeline.states[-1].position.board
        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        next_board = board.copy()
        next_board.push(candidate)
        next_state = BoardState(
            index=len(self.timeline.states),
            position=Position(board=next_board, side_to_move="white" if next_board.turn == chess.WHITE else "black"),
            move=None,
        )
        self.timeline.states.append(next_state)
        self.action_log.append(actor, "PresentMove", None, self.config_hash)
        self.turn_index += 1
        self.pending_actor = self.current_player
        self._evaluate_marks()
        self.resolve_waves()
        return next_state

    def edit_past(self, actor: str, index: int, move: chess.Move | str) -> None:
        if not self._is_own_ply(actor, index):
            raise GameError("ERR_NOT_YOUR_PLY", f"Only {self._player_owner_for_state_index(index)} may edit this ply.")
        if self.frozen_board is not None and index >= self.frozen_board:
            raise GameError("ERR_EDIT_AT_OR_AFTER_FROZEN", "Edits are only allowed below the frozen board.")

        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        board = self._board_at_index(index)
        if candidate not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Edit move is illegal in the target position.")

        cost = self.cost_model.cost(len(self.timeline.states) - 1, index)
        if self.players[actor].energy < cost:
            raise GameError("ERR_INSUFFICIENT_ENERGY", f"Need {cost}, have {self.players[actor].energy}.")

        self.players[actor].energy -= cost
        self.timeline.states[index].move = candidate
        self._apply_payment(actor, "black" if actor == "white" else "white", cost, self.config.transfer_pct_edit)
        self.action_log.append(actor, "PastEdit", None, self.config_hash)
        self.waves.append(Wave(id=len(self.waves), origin=index, front=index))
        self.resolve_waves()

    def respond(self, actor: str, index: int, move: chess.Move | str) -> None:
        candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
        board = self._board_at_index(index)
        if candidate not in board.legal_moves:
            raise GameError("ERR_ILLEGAL_MOVE", "Response move is illegal.")

        cost = self.cost_model.cost(len(self.timeline.states) - 1, index)
        paid = min(self.players[actor].energy, cost)
        self.players[actor].energy -= paid
        self.timeline.states[index].move = candidate
        self.action_log.append(actor, "Respond", None, self.config_hash)
        if paid > 0:
            self._apply_payment(actor, "black" if actor == "white" else "white", paid, self.config.transfer_pct_response)

    def pass_turn(self, actor: str) -> None:
        if self.frozen_board is None:
            raise GameError("ERR_PASS_NOT_ALLOWED", "Pass is allowed only while the game is frozen.")
        self.action_log.append(actor, "Pass", None, self.config_hash)

    def resolve_waves(self) -> None:
        if not self.waves:
            return
        for wave in list(self.waves):
            if wave.halted:
                continue
            steps_taken = 0
            while steps_taken < self.config.WAVE_STEPS_PER_TURN and wave.front < len(self.timeline.states) - 1:
                current_state = self.timeline.states[wave.front]
                next_board = current_state.position.board.copy()
                recorded_move = current_state.move
                if recorded_move is not None:
                    try:
                        if recorded_move in next_board.legal_moves:
                            next_board.push(recorded_move)
                        else:
                            # Illegal recorded move is left in place but the wave marks the state as invalid.
                            wave.halted = True
                            break
                    except Exception:
                        wave.halted = True
                        break
                if current_state.move is None:
                    wave.front += 1
                    steps_taken += 1
                    continue

                wave.front += 1
                steps_taken += 1
                if wave.front >= len(self.timeline.states):
                    break
                if wave.front == len(self.timeline.states) - 1:
                    break
            self._evaluate_marks()

    def legal_responses(self, index: int) -> list[chess.Move]:
        return list(self._board_at_index(index).legal_moves)

    def board_view(self, index: int) -> BoardView:
        state = self.timeline.states[index]
        return BoardView(now=state.position.board, projected=state.position.board, status="certain")

    def forecast(self) -> Forecast:
        return Forecast(
            positions=[state.position.board for state in self.timeline.states],
            eta=[0 for _ in self.timeline.states],
            stall_points=[None for _ in self.timeline.states],
        )

    def serialize(self) -> dict[str, Any]:
        payload = {
            "turn_index": self.turn_index,
            "pending_actor": self.pending_actor,
            "frozen_board": self.frozen_board,
            "players": {color: {"color": p.color, "energy": p.energy} for color, p in self.players.items()},
            "timeline": [
                {
                    "index": state.index,
                    "fen": state.position.board.fen(),
                    "move": state.move.uci() if state.move is not None else None,
                }
                for state in self.timeline.states
            ],
            "marks": [{"index": m.index, "kind": m.kind} for m in self.marks],
            "waves": [{"id": w.id, "origin": w.origin, "front": w.front, "halted": w.halted} for w in self.waves],
        }
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Game":
        game = cls()
        game.turn_index = payload.get("turn_index", 0)
        game.pending_actor = payload.get("pending_actor", "white")
        game.frozen_board = payload.get("frozen_board")
        if payload.get("players"):
            for color, details in payload["players"].items():
                game.players[color] = Player(color=color, energy=int(details["energy"]))
        for entry in payload.get("timeline", []):
            board = chess.Board(entry["fen"])
            move = chess.Move.from_uci(entry["move"]) if entry.get("move") else None
            game.timeline.append_state(Position(board=board, side_to_move="white" if board.turn == chess.WHITE else "black"), move)
        game.marks = [Mark(index=m["index"], kind=m["kind"]) for m in payload.get("marks", [])]
        game.waves = [Wave(id=w["id"], origin=w["origin"], front=w["front"], halted=w.get("halted", False)) for w in payload.get("waves", [])]
        return game
