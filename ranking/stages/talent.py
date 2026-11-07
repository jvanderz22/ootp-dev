"""The fitted talent layer (phase 3: hitters). `LegacyModel` asks it for each
batch's batting scores: it scores every player whose base batting ratings are
all there, and the legacy batting model scores the rest (old class formats
without BABIP).

Until the value layer turns everything into WAR, the fitted wRC+ is put on the
legacy batting model's 0-100 scale through the artifact's points bridge, so the
fielding and running components, the modifiers and the two-way rule still see
the scale they were tuned for.
"""
from typing import NamedTuple

import numpy as np

from ranking import hitter_talent
from ranking.ratings import RatingsView
from scoring.runtime_components import write_runtime_component


class FittedBatting(NamedTuple):
    points: float
    label: str


class HitterTalent:
    name = "hitter-talent"

    def __init__(self, profile, model=None):
        self.ratings = RatingsView(profile.ratings)
        self.model = model or hitter_talent.load()

    @property
    def artifact(self) -> str:
        return self.model.version

    def score(self, players) -> list:
        """A FittedBatting per player, or None where the ratings aren't there."""
        out = [None] * len(players)
        rated = [(i, r) for i, p in enumerate(players) if (r := self.ratings.hitting(p)) is not None]
        if not rated:
            return out
        ratings = {name: np.array([r[name] for _, r in rated]) for name in hitter_talent.RATINGS}
        wrc_plus = self.model.wrc_plus(ratings)
        points = self.model.points(wrc_plus)
        for (i, _), wrc, pts in zip(rated, wrc_plus, points):
            write_runtime_component(players[i].id, "batting.talent.wrc_plus", float(wrc))
            out[i] = FittedBatting(float(pts), f"batting talent ({wrc:.0f} wRC+)")
        return out
