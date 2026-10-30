from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceConfig:
    WAVE_STEPS_PER_TURN: int = 3
    ENERGY_SCALE: int = 100
    regen_per_turn: int = 100
    start_energy: dict[str, int] = None
    max_energy: dict[str, int] = None
    cost_per_turn_back: int = 100
    transfer_pct_edit: int = 0
    transfer_pct_response: int = 0

    def __post_init__(self) -> None:
        if self.start_energy is None:
            object.__setattr__(self, "start_energy", {"white": 0, "black": 100})
        if self.max_energy is None:
            object.__setattr__(self, "max_energy", {"white": 600, "black": 700})

    @classmethod
    def default(cls) -> "BalanceConfig":
        return cls()
