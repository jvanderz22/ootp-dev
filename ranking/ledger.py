"""A player's step-by-step score record.

Every stage appends lines - what it was, which side it was on, how much it moved
the score - and the counted lines sum to the final score. Lines for the side a
player isn't judged on are kept (so the card can show both) but not counted.

Units are legacy score points until the value layer turns them into WAR.
"""
from typing import NamedTuple

MODEL = "model"
MODIFIERS = "modifiers"
DEVELOPMENT = "development"
TWO_WAY = "two-way"
DEMAND = "demand"

BATTING = "batting"
PITCHING = "pitching"


class LedgerLine(NamedTuple):
    stage: str
    label: str
    delta: float
    side: str = None   # BATTING / PITCHING; None once the sides are combined


class Ledger:
    """Lines are tuples so a whole league's ledgers stay small."""

    __slots__ = ("lines", "side")

    def __init__(self):
        self.lines = []
        # the side the player is judged on, set when the sides are combined
        self.side = None

    def add(self, stage, label, delta, side=None) -> None:
        self.lines.append(LedgerLine(stage, label, float(delta), side))

    def scale(self, stage, label, value, factor, side=None) -> float:
        """Record `value` x `factor` as a line of `value * (factor - 1)`; returns
        the scaled value."""
        self.add(stage, label, value * (factor - 1), side)
        return value * factor

    def counted(self, line) -> bool:
        return line.side is None or line.side == self.side

    def total(self) -> float:
        return sum(line.delta for line in self.lines if self.counted(line))

    def as_list(self) -> list:
        return [{**line._asdict(), "counted": self.counted(line)} for line in self.lines]
