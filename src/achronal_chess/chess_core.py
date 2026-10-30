from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import chess

from .config import BalanceConfig

__all__ = [
    "Position",
    "legal_moves",
    "is_legal_move",
    "is_checkmate",
    "is_stalemate",
    "is_draw",
    "detect_marks",
    "apply_move",
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
            rights = ""
            if self.board.has_kingside_castling_rights(chess.WHITE):
                rights += "K"
            if self.board.has_queenside_castling_rights(chess.WHITE):
                rights += "Q"
            if self.board.has_kingside_castling_rights(chess.BLACK):
                rights += "k"
            if self.board.has_queenside_castling_rights(chess.BLACK):
                rights += "q"
            self.castling = rights
        if self.en_passant is None:
            self.en_passant = chess.square_name(self.board.ep_square) if self.board.ep_square is not None else None
        self.hash = hash(self.board.fen())


def apply_move(board: chess.Board, move: chess.Move | str) -> chess.Board:
    next_board = board.copy()
    candidate = chess.Move.from_uci(move) if isinstance(move, str) else move
    next_board.push(candidate)
    return next_board


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
    return (
        board.is_insufficient_material()
        or board.is_seventy_five_moves()
        or board.is_fivefold_repetition()
        or board.is_repetition(3)
    )


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
