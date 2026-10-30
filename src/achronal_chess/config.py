from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BalanceConfig:
    WAVE_STEPS_PER_TURN: int = 3
    ENERGY_SCALE: int = 100
    regen_per_turn: int = 100
    start_energy: dict[str, int] = field(default_factory=lambda: {"white": 0, "black": 100})
    max_energy: dict[str, int] = field(default_factory=lambda: {"white": 600, "black": 700})
    cost_per_turn_back: int = 100
    transfer_pct_edit: int = 0
    transfer_pct_response: int = 0

    @classmethod
    def default(cls) -> "BalanceConfig":
        return cls()
