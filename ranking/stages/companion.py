"""Scores each batch on a second profile alongside the ranked one, and keeps
what it's worth there: his ceiling (his potential ratings' full-time WAR),
or his current ratings' WAR in a full-time role next to his value at the
roster spot he'd fill.

The companion runs its own talent and value stages on its own states, and
inside its own breakdown scope, so nothing it records reaches the ranked
profile's card. It isn't in the ranked profile's ledger or order either -
only his WAR and role there are kept, on `state.companions[key]`.
"""
from typing import NamedTuple

from ranking import value
from ranking.ledger import BATTING, MODEL, PITCHING
from ranking.stages.base import BatchStage
from ranking.stages.talent import Talent
from ranking.stages.value import Value
from ranking.state import PlayerState
from scoring.runtime_components import runtime_components_scope

# a hitter's bat on the ledger (ranking/stages/value.py): what develops - his
# glove and legs have no potential ratings
BAT_LINES = ("batting", "platoon")


class CompanionValue(NamedTuple):
    war: float
    # where he's valued there: his best position, or SP / RP
    role: str
    # his WAR from the model lines alone, before any modifier or the two-way
    # credit (the draft odds read readiness this way, as they were fit)
    model: float
    # the same for each side, BATTING and PITCHING: the odds read a side's
    # readiness off that side, so a ready bat doesn't lift his pitching
    sides: dict = None
    # his bat's WAR alone (BAT_LINES): how developed a hitter is, as the
    # prospect odds read it
    bat: float = None


class Companion(BatchStage):
    name = "companion"

    def __init__(self, key, profile, league=None):
        self.key = key
        self.profile = profile
        self.stages = [Talent(profile), Value(profile, league=league)]

    @property
    def artifacts(self) -> dict:
        out = {}
        for stage in self.stages:
            out.update(stage.artifacts)
        return out

    def run(self, states, profile):
        shadows = [PlayerState(state.player) for state in states]
        with runtime_components_scope():
            for stage in self.stages:
                stage.run(shadows, self.profile)
        for state, shadow in zip(states, shadows):
            ledger = shadow.ledger
            model = sum(line.delta for line in ledger.lines if line.stage == MODEL and ledger.counted(line))
            sides = {side: float(sum(line.delta for line in ledger.lines if line.stage == MODEL and line.side == side)
                                 / value.DISPLAY_SCALE) for side in (BATTING, PITCHING)}
            bat = sum(line.delta for line in ledger.lines
                      if line.stage == MODEL and line.side == BATTING and line.label in BAT_LINES)
            state.companions[self.key] = CompanionValue(
                float((shadow.value - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE), ledger.role,
                float((model - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE), sides, float(bat / value.DISPLAY_SCALE))
