"""The fielding talent model: your position grids -> fielding runs per season.

Your grids (attribute_models/*_attribute_model.py) stay the shape of defense:
at each position, the grid score decides who the better fielder is, and it
already weighs Arm, Error and Turn DP the way you want. Two things go on top:

- Position floors (decided 2026-11-08): below a floor a player can't be
  trusted at the position. The grid score is scaled down over the last
  FLOOR_RAMP points above the floor, to half at the floor itself and to
  nothing below it (ratings move in steps of 5). A wider ramp moved everyday
  MLB shortstops with a 50 Error or Turn DP, good ones by zone rating, off SS.
- One line, the same at every position, turning a floored grid score into
  fielding value: runs per season (SEASON_INNINGS) including the position's
  adjustment, fit to MLB zone rating + framing plus StatsPlus's adjustments.

Your grids already compare positions on one scale (a 70 Range outfielder grades
higher at CF than at LF, because CF is worth more; decided 2026-11-08), so the
best position is the highest floored grid score, as in legacy, and it is also
the most valuable. A grid of 0 ("can't play there") comes out about at DH.

The utility bonus is legacy's (scoring/position_player_scorer.py), on the
floored grid scores: a position below its floor doesn't count toward it.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking import bridge
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "fielding_talent_v1"
POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
SEASON_INNINGS = 1350
# position -> {rating: floor}
FLOORS = {
    "SS": {"if_arm": 45, "if_error": 45, "turn_dp": 45},
    "3B": {"if_arm": 45, "if_error": 40},
    "2B": {"turn_dp": 40},
    "RF": {"of_arm": 45},
    "CF": {"of_range": 55},
    "C": {"c_blocking": 40, "c_framing": 40},
}
FLOOR_RAMP = 5
RATINGS = (
    "c_arm", "c_blocking", "c_framing", "if_range", "if_arm", "if_error", "turn_dp",
    "of_range", "of_arm", "of_error",
)
# a step below the floor is where the factor reaches 0
BELOW_FLOOR = 5


def floor_factor(position, ratings: dict):
    """1 at FLOOR_RAMP points or more above every floor, half at the lowest
    one, 0 below it."""
    factor = np.ones(len(next(iter(ratings.values()))))
    for rating, floor in FLOORS.get(position, {}).items():
        ramp = (np.asarray(ratings[rating]) - (floor - BELOW_FLOOR)) / (FLOOR_RAMP + BELOW_FLOOR)
        factor = np.minimum(factor, np.clip(ramp, 0, 1))
    return factor


def floored_grids(grids: dict, ratings: dict) -> dict:
    """{position: grid score scaled by its floor factor}."""
    return {pos: np.asarray(grids[pos]) * floor_factor(pos, ratings) for pos in POSITIONS}


class FieldingTalent:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.intercept = artifact["value_line"]["intercept"]
        self.slope = artifact["value_line"]["slope"]
        self.position_adjustment = artifact["position_adjustment"]
        # best-position runs -> legacy fielding points; absent while fitting
        self.bridge = artifact.get("points_bridge")

    @classmethod
    def from_file(cls, path) -> "FieldingTalent":
        return cls(json.loads(Path(path).read_text()))

    def value(self, floored: dict) -> dict:
        """{position: fielding runs per season there, plus its adjustment}."""
        return {pos: self.intercept + self.slope * np.asarray(floored[pos]) for pos in POSITIONS}

    def runs(self, floored: dict) -> dict:
        """{position: fielding runs per season against an average fielder there}."""
        return {pos: v - self.position_adjustment[pos] for pos, v in self.value(floored).items()}

    def best(self, floored: dict):
        """(value at the best position, that position, his fielding runs there).
        The best position has the highest floored grid score."""
        index = np.column_stack([floored[pos] for pos in POSITIONS]).argmax(axis=1)
        best = [POSITIONS[i] for i in index]
        value = self.intercept + self.slope * np.array([floored[pos][j] for j, pos in enumerate(best)])
        adjustment = np.array([self.position_adjustment[pos] for pos in best])
        return value, best, value - adjustment

    def points(self, value):
        return bridge.points(value, self.bridge)


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> FieldingTalent:
    return FieldingTalent.from_file(ARTIFACTS_DIR / f"{name}.json")


def grid_scores(players) -> dict:
    """{position: your grid's score for each player} (legacy fielding models)."""
    from scoring.model_cache import get_position_player_scorer

    models = get_position_player_scorer("overall").fielding_models_map
    return {pos: np.asarray(models[pos].predict_many(players)) for pos in POSITIONS}


def ratings_of(players) -> dict:
    return {r: np.array([getattr(p, r) for p in players]) for r in RATINGS}
