from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import BalanceConfig

__all__ = [
    "Player",
    "Mark",
    "BoardState",
    "Timeline",
    "Wave",
    "ActionLog",
    "GameError",
    "PresentMove",
    "PastEdit",
    "Respond",
    "Pass",
    "BoardView",
    "Forecast",
]


@dataclass
class Player:
    color: str
    energy: int


@dataclass
class Mark:
    index: int
    kind: str


@dataclass
class BoardState:
    index: int
    position: Any
    move: Any | None = None


@dataclass
class Timeline:
    states: list[BoardState] = field(default_factory=list)

    def append_state(self, position: Any, move: Any | None = None) -> BoardState:
        state = BoardState(index=len(self.states), position=position, move=move)
        self.states.append(state)
        return state

    def replace_move(self, index: int, new_move: Any | None) -> None:
        if index < 0 or index >= len(self.states):
            raise IndexError(f"State index {index} out of range")
        self.states[index].move = new_move

    def board_at(self, index: int) -> BoardState:
        return self.states[index]


@dataclass
class Wave:
    id: int
    origin: int
    front: int
    halted: bool = False


@dataclass
class ActionLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def append(self, actor: str, action: str, tick: int | None, config_hash: str) -> None:
        self.entries.append({
            "actor": actor,
            "action": action,
            "tick": tick,
            "config_hash": config_hash,
        })


class GameError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class PresentMove:
    move: Any


@dataclass
class PastEdit:
    index: int
    move: Any


@dataclass
class Respond:
    index: int
    move: Any


@dataclass
class Pass:
    pass


@dataclass
class BoardView:
    now: Any
    projected: Any
    status: str = "certain"


@dataclass
class Forecast:
    positions: list[Any]
    eta: list[int]
    stall_points: list[int | None]
