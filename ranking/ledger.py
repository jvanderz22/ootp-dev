"""A player's step-by-step score record.

Every stage appends lines - what it was, which side it was on, how much it moved
the score - and the counted lines sum to the final score. Lines for the side a
player isn't judged on are kept (so the card can show both) but not counted.

Units are legacy score points until the value layer turns them into WAR.

A line's label is a short name ("batting", "fielding"); what it read goes in
`stat`, the headline number ("105 wRC+"), and `note`, the context behind it
("vL 92 · vR 112, +3.5 runs") - so the card can lay them out, and `text` gives
the one-line form for reports.
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
    stat: str = None   # the headline of what it read, e.g. "105 wRC+"
    note: str = None   # the context behind it, e.g. "vL 92 · vR 112"

    @property
    def text(self) -> str:
        """The label with its stat and note, on one line."""
        detail = ", ".join(x for x in (self.stat, self.note) if x)
        return f"{self.label} ({detail})" if detail else self.label


class Ledger:
    """Lines are tuples so a whole league's ledgers stay small."""

    __slots__ = ("lines", "side", "role")

    def __init__(self):
        self.lines = []
        # the side the player is judged on, set when the sides are combined
        self.side = None
        # where he's valued on that side: his best position, or SP / RP
        self.role = None

    def add(self, stage, label, delta, side=None, stat=None, note=None) -> None:
        self.lines.append(LedgerLine(stage, label, float(delta), side, stat, note))

    def scale(self, stage, label, value, factor, side=None, note=None) -> float:
        """Record `value` x `factor` as a line of `value * (factor - 1)`; returns
        the scaled value."""
        self.add(stage, label, value * (factor - 1), side, f"x{factor:.2f}", note)
        return value * factor

    def counted(self, line) -> bool:
        return line.side is None or line.side == self.side

    def total(self) -> float:
        return sum(line.delta for line in self.lines if self.counted(line))

    def as_list(self) -> list:
        return [{**line._asdict(), "counted": self.counted(line)} for line in self.lines]
