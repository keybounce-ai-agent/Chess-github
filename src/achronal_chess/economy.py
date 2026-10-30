from __future__ import annotations

import math
from dataclasses import dataclass

from .config import BalanceConfig

__all__ = [
    "CostModel",
    "apply_payment",
    "regen_for_turn",
]


@dataclass
class CostModel:
    config: BalanceConfig

    def cost(self, present_index: int, past_index: int) -> int:
        if past_index < 0:
            return 0
        distance = present_index - past_index
        if distance <= 0:
            return 0
        turns_back = math.ceil(distance / 2)
        return turns_back * self.config.cost_per_turn_back

    def regen_increment(self, current_energy: int, cap: int) -> int:
        return min(self.config.regen_per_turn, max(0, cap - current_energy))


def apply_payment(payer_energy: int, recipient_energy: int, amount: int, transfer_pct: int, cap: int) -> tuple[int, int, int]:
    paid = max(0, min(payer_energy, amount))
    if paid <= 0:
        return payer_energy, recipient_energy, 0

    transfer = (paid * transfer_pct) // 100
    transfer = min(transfer, max(0, cap - recipient_energy))
    recipient_energy = min(cap, recipient_energy + transfer)
    payer_energy -= paid
    destroyed = paid - transfer
    return payer_energy, recipient_energy, destroyed


def regen_for_turn(current_energy: int, cap: int, regen_per_turn: int) -> int:
    return min(cap, current_energy + regen_per_turn)
