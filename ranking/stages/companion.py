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
from ranking.stages.base import BatchStage
from ranking.stages.talent import Talent
from ranking.stages.value import Value
from ranking.state import PlayerState
from scoring.runtime_components import runtime_components_scope


class CompanionValue(NamedTuple):
    war: float
    # where he's valued there: his best position, or SP / RP
    role: str


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
            war = float((shadow.value - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE)
            state.companions[self.key] = CompanionValue(war, shadow.ledger.role)
