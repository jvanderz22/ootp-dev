"""The fielding talent model: ratings -> fielding runs per season at each
position, from lookup tables (decided 2026-11-09; plans/xgboost-phaseout-plan.md,
step 2).

Each position has a table per rating it reads: runs per season (SEASON_INNINGS)
against the average fielder there, at every 5-point step, straight between
steps. A position's runs are the sum of its tables. The stats seed them
(ranking/fitting/fielding_talent.py: zone runs, framing for C, double plays for
2B and SS), and your judgment replaces a table where the stats can't measure it
(JUDGED): CF's Range curve, and outfield Arm, which StatsPlus's arm runs don't
track (about three times CF's weight in RF, half of it in LF).

Position floors (decided 2026-11-08, moved 2026-11-09; a catcher's Arm at 35,
since Arm 40 cost good framers like Contreras most of their value): below a floor a player
can't be trusted at the position. His value there falls toward a DH's over the
last FLOOR_RAMP points above the floor: half at the floor itself, a DH's one
step below it (ratings move in steps of 5). A left-handed thrower is below
the floor at C, 2B, 3B and SS (RIGHT_HANDED; decided 2026-11-10).

The value of a position is its runs plus its adjustment. The adjustments come
from where OOTP's managers play regulars, pulled lightly toward StatsPlus's
(decided 2026-11-09): StatsPlus's put SS only 2 runs above 2B, so a true SS
came out worth more at 2B. The best position is the most valuable one, so the
same adjustments pick a player's position and value him there. The corners
are one skill apart from the arm (2026-11-09): LF and RF share their Range and
Error shapes, and RF's adjustment sits a little above LF's (a ball that gets
by in RF puts runners on third), so an outfielder with an arm is worth more in
RF than LF.

Utility (decided 2026-11-09) is roster flexibility, not runs: WAR for other
positions a player can cover - one in the middle infield (SS over 2B), one in
the outfield (CF over RF over LF), and 3B - sized by you (UTILITY_WAR).
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "fielding_talent_v2"
POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
SEASON_INNINGS = 1350
STEPS = tuple(range(20, 81, 5))
RATINGS = (
    "c_arm", "c_blocking", "c_framing", "if_range", "if_arm", "if_error", "turn_dp",
    "of_range", "of_arm", "of_error",
)
# position -> {rating: floor}
FLOORS = {
    "SS": {"if_arm": 45, "if_error": 45, "turn_dp": 40},
    "3B": {"if_arm": 45, "if_error": 40},
    "2B": {"turn_dp": 35},
    "RF": {"of_arm": 45},
    "CF": {"of_range": 55},
    "C": {"c_arm": 35, "c_blocking": 45, "c_framing": 40},
}
# positions a left-handed thrower can't play: below the floor whatever his ratings
RIGHT_HANDED = ("C", "2B", "3B", "SS")
LEFTY = "throws_left"
FLOOR_RAMP = 5
# a step below the floor is where the factor reaches 0
BELOW_FLOOR = 5


def _edges(per_step, low=45, high=60):
    """Runs at STEPS: `per_step` per 5 points above `high`, the same off per 5
    points below `low`, 0 between."""
    return [per_step * (max(s - high, 0) - max(low - s, 0)) / 5 for s in STEPS]


# your judgment where the stats can't measure it: {position: {rating: runs at STEPS}}
JUDGED = {
    "CF": {
        # your CF rule (2026-11-08): 60 or less can't start, 65 playable but below
        # average, 70 good, 75 very good - the runs it came to, calibrated
        "of_range": [-23.0] * 7 + [-22.0, -19.0, -6.0, 7.0, 13.0, 18.0],
        "of_arm": _edges(0.5),
        # Error only at 30 or below
        "of_error": [-1.5, -1.0, -0.5] + [0.0] * 10,
    },
    "LF": {"of_arm": _edges(0.25)},
    # RF's Arm costs from below 55 (2026-11-09): with RF a little more valuable
    # than LF, a 45 arm always plays LF and a 50 mostly does
    "RF": {"of_arm": _edges(1.5, low=55)},
}
# utility: WAR for each other position he covers - clears its floors and
# fields it no worse than COVER_RUNS against its average
COVER_RUNS = -10.0
UTILITY_WAR = {"SS": 0.15, "2B": 0.08, "3B": 0.08, "CF": 0.15, "RF": 0.05, "LF": 0.04}
UTILITY_GROUPS = (("SS", "2B"), ("3B",), ("CF", "RF", "LF"))
# 3B's credit when he's a shortstop or covers SS
SS_COVERS_3B = 0.5


def floor_factor(position, ratings: dict):
    """1 at FLOOR_RAMP points or more above every floor, half at the lowest
    one, 0 below it - and 0 for a left-handed thrower at RIGHT_HANDED."""
    factor = np.ones(len(next(iter(ratings.values()))))
    for rating, floor in FLOORS.get(position, {}).items():
        ramp = (np.asarray(ratings[rating], float) - (floor - BELOW_FLOOR)) / (FLOOR_RAMP + BELOW_FLOOR)
        factor = np.minimum(factor, np.clip(ramp, 0, 1))
    if position in RIGHT_HANDED and LEFTY in ratings:
        factor = np.where(np.asarray(ratings[LEFTY], bool), 0.0, factor)
    return factor


class FieldingTalent:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.tables = {
            pos: {rating: np.asarray(JUDGED.get(pos, {}).get(rating, t), float) for rating, t in tables.items()}
            for pos, tables in artifact["tables"].items()
        }
        for pos, judged in JUDGED.items():
            for rating, t in judged.items():
                self.tables[pos].setdefault(rating, np.asarray(t, float))
        self.position_adjustment = artifact["position_adjustment"]
        self.dh_adjustment = artifact["dh_adjustment"]

    @classmethod
    def from_file(cls, path) -> "FieldingTalent":
        return cls(json.loads(Path(path).read_text()))

    def unfloored(self, ratings: dict) -> dict:
        """{position: runs per season there against its average fielder}."""
        return {pos: sum(np.interp(np.asarray(ratings[r], float), STEPS, t) for r, t in tables.items())
                for pos, tables in self.tables.items()}

    def value(self, ratings: dict) -> dict:
        """{position: runs there plus its adjustment}, falling toward a DH's
        below its floors."""
        out = {}
        for pos, runs in self.unfloored(ratings).items():
            f = floor_factor(pos, ratings)
            out[pos] = f * (runs + self.position_adjustment[pos]) + (1 - f) * self.dh_adjustment
        return out

    def runs(self, ratings: dict) -> dict:
        """{position: runs against its average fielder, after its floors}."""
        return {pos: v - self.position_adjustment[pos] for pos, v in self.value(ratings).items()}

    def best(self, ratings: dict):
        """(value at the best position, that position, his runs there): the
        most valuable position."""
        value = self.value(ratings)
        index = np.column_stack([value[pos] for pos in POSITIONS]).argmax(axis=1)
        best = [POSITIONS[i] for i in index]
        top = np.array([value[pos][j] for j, pos in enumerate(best)])
        adjustment = np.array([self.position_adjustment[pos] for pos in best])
        return top, best, top - adjustment

    def covers(self, ratings: dict) -> dict:
        """{position: whether each player can cover it}."""
        runs = self.unfloored(ratings)
        return {pos: (floor_factor(pos, ratings) >= 1) & (runs[pos] >= COVER_RUNS) for pos in POSITIONS}


def utility(covers: set, best: str) -> tuple:
    """(WAR, the positions credited) for a player whose best position is
    `best` and who covers `covers`."""
    war, credited = 0.0, []
    for group in UTILITY_GROUPS:
        # within a group only a position above his own counts
        above = group[:group.index(best)] if best in group else group
        pos = next((p for p in above if p in covers), None)
        if pos is None:
            continue
        credit = UTILITY_WAR[pos]
        if pos == "3B" and (best == "SS" or "SS" in credited):
            credit *= SS_COVERS_3B
        war += credit
        credited.append(pos)
    return war, credited


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> FieldingTalent:
    return FieldingTalent.from_file(ARTIFACTS_DIR / f"{name}.json")


def lefty(players) -> np.ndarray:
    """1 for a left-handed thrower, else 0 (right, switch or not exported)."""
    return np.array([(p.throw_hand or "").strip()[:1].upper() == "L" for p in players], float)


def ratings_of(players) -> dict:
    return {**{r: np.array([getattr(p, r) or 0 for p in players], float) for r in RATINGS}, LEFTY: lefty(players)}
