"""The value layer (phase 5b): talent -> WAR at a full-time role, shown as points.

Every player is valued at a full-time role, not his expected playing time
(decided 2026-11-08): an everyday hitter, a starter at the innings his stamina
carries, or a reliever. Per-run and per-inning values are StatsPlus's own,
taken apart by ranking.fitting.value:

    hitter    per batting run x batting runs (wRC+ over a full season's PA)
              + per defense run x (fielding value with its position adjustment
              + baserunning runs) + the position-player allowance
    starter   per run x runs saved against the league ERA + per nine innings,
              over starts x innings a start by stamina, at the matchups
              lineups give him (`matchup_tilt`); he needs
              STARTER_MIN_STAMINA and STARTER_MIN_PITCHES
    reliever  the same over a reliever's innings, his runs saved counted at
              LEVERAGE_WEIGHT of the leverage his talent earns him (an optimal
              manager gives the best reliever the biggest spots), and at the
              matchups you'd give him (`matchup_tilt`)

Matchups follow a pitcher's split (2026-11-08): none for an even split,
MATCHUP_TILT of the batters moved at FULL_TILT_SPLIT (runs index, about the
95th percentile of the snapshot's pitchers) and above, a straight ramp
between. A reliever is used the way you use him, so they move to his strong
side; a starter can't pick his batters and lineups stack his weak side, so
they move there. A big split costs a starter what it earns a reliever, by
the innings each pitches - a set cost by split, not a share of his value -
and the better of the two roles moves a big-split starter to the bullpen
when that's worth more.

Each talent read is calibrated against what MLB regulars actually did
(`calibration`, fit by ranking.fitting.value on the snapshot's season):
actual = a + b x predicted, for wRC+, baserunning runs, and each role's ERA
(against FIP, which StatsPlus's WAR runs on). Fielding is calibrated within
each position, apart from the position's adjustment (2026-11-08): fielding
runs against an average fielder there = the position's level + one pooled
stretch x predicted. Within a position the grids' runs were too compressed
(real fielders spread ~1.2x wider), while some positions' levels were off
(MLB centre fielders ~6 runs too high, third basemen ~6 too low); fit
together with the adjustments, they had shrunk every good defender. Each
position's adjustment then shifts by what its regulars' WAR says it's worth. The
talent models rank well but their spread was off - baserunning too wide,
pitchers too narrow and starters too optimistic. A starter's innings per start come from his stamina and how
efficient he is - his walks, strikeouts and home runs per PA (walks drive
pitches per inning): a stingy starter goes deeper than his stamina says.

A pitcher's value above replacement is floored on Control (decided
2026-11-08, your pitcher rule 5 back as a floor like the position floors):
full from CONTROL_FLOOR + FLOOR_RAMP, half at CONTROL_FLOOR, nothing a step
below it. MLB pitchers at Control 30 or less were below replacement in 2042
(-0.8 WAR per 100 IP); 31-35 barely above (+0.3), 36-40 +0.5. A floor at 35
zeroed a Control-30 prospect (Henry MacGregor, #63 -> #492), too much for a
potential rating, so it sits at 30: half value there (#232).

No extra weight on pitchers against hitters (your call, 2026-11-08): with
the tables' tails continued and starters' depth from their efficiency, Andy
Spinner is the best pitcher in the league and #2 overall on current ratings.

A two-way player gets his better side plus a share of the other side's WAR
above replacement (`two_way_share`): none while the other side is only
marginal (TWO_WAY_FLOOR WAR or less - a back-end starter, a bench bat), the
full TWO_WAY_SHARE from TWO_WAY_FULL WAR (about a league-average full-time
starter), and a straight ramp between. A decent batter shouldn't outrank
better batters for being a decent AAA pitcher.

On screen, `points` = 50 + 10 x WAR (50 = replacement).
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "value_v1"
# judgment (2026-11-08)
LEVERAGE_WEIGHT = 1.0   # full leverage, the most the stats support
TWO_WAY_SHARE = 0.2
TWO_WAY_FLOOR, TWO_WAY_FULL = 1.75, 2.5   # the other side's WAR
MATCHUP_TILT, FULL_TILT_SPLIT = 0.20, 20.0
CONTROL_FLOOR, FLOOR_RAMP = 30, 5
STARTER_MIN_STAMINA = 35   # borderline, at the bottom of the innings curve
STARTER_MIN_PITCHES = 3
DISPLAY_OFFSET, DISPLAY_SCALE = 50.0, 10.0
# legacy modifiers the hitter platoons (ranking/stages/value.py) replace
PLATOON_REPLACES = ("BatterHandednessModifier",)


def points(war):
    return DISPLAY_OFFSET + DISPLAY_SCALE * np.asarray(war)


def control_floor(control) -> float:
    """The share of a pitcher's value above replacement his Control keeps."""
    ramp = (control - (CONTROL_FLOOR - FLOOR_RAMP)) / (2 * FLOOR_RAMP)
    return float(np.clip(ramp, 0.0, 1.0))


def two_way_share(other_war) -> float:
    """The share of his other side's WAR a two-way player is credited."""
    ramp = (other_war - TWO_WAY_FLOOR) / (TWO_WAY_FULL - TWO_WAY_FLOOR)
    return TWO_WAY_SHARE * float(np.clip(ramp, 0.0, 1.0))


def matchup_tilt(split) -> float:
    """The share of a pitcher's batters moved to his strong side (relieving) or
    his weak side (starting), for a split of `split` runs index (either
    direction)."""
    return MATCHUP_TILT * float(np.clip(abs(split) / FULL_TILT_SPLIT, 0.0, 1.0))


class ValueModel:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.hitter = artifact["hitter"]
        self.pitcher = artifact["pitcher"]
        self.workloads = artifact["workloads"]
        self.leverage_map = artifact["leverage"]
        # {"wrc_plus" | "baserunning": [a, b], "era": {role: [a, b]},
        #  "fielding": {"per_run": b, "by_position": {position: a},
        #               "position_shift": {position: runs}}}
        self.calibration = artifact.get("calibration")

    @classmethod
    def from_file(cls, path) -> "ValueModel":
        return cls(json.loads(Path(path).read_text()))

    @property
    def hitter_pa(self) -> float:
        return self.workloads["hitter_pa"]

    def hitting(self, batting_runs, fielding_value, baserunning_runs) -> dict:
        """WAR parts for a full season: batting runs over hitter_pa, fielding
        value a season with its position adjustment, baserunning runs over
        hitter_pa."""
        h, share = self.hitter, self.hitter_pa / 600
        return {
            "batting": h["per_batting_run"] * batting_runs,
            "fielding": h["per_defense_run"] * fielding_value,
            "running": h["per_defense_run"] * baserunning_runs,
            "allowance": h["allowance_600"] * share,
        }

    def calibrated(self, name, predicted, role=None):
        """`predicted` (wRC+, baserunning runs, or `role`'s ERA) on the scale
        MLB regulars actually played at."""
        fit = (self.calibration or {}).get(name)
        if fit is None:
            return predicted
        a, b = fit[role] if role else fit
        return a + b * np.asarray(predicted)

    def fielding_runs(self, runs, position) -> float:
        """Fielding runs against an average fielder at `position`, as MLB
        fielders there actually played to them."""
        fit = (self.calibration or {}).get("fielding")
        if fit is None:
            return runs
        return fit["by_position"][position] + fit["per_run"] * runs

    def position_shift(self, position) -> float:
        """Runs to add to `position`'s adjustment, from what MLB regulars
        there were worth beyond it."""
        return ((self.calibration or {}).get("fielding") or {}).get("position_shift", {}).get(position, 0.0)

    def starter_innings(self, stamina, pitches, rates=None) -> float:
        """A full-time starter's innings, from his stamina and his starter
        `rates` ({"k" | "bb" | "hr": per PA}; league-typical when None), or 0
        when he can't start."""
        if stamina < STARTER_MIN_STAMINA or pitches < STARTER_MIN_PITCHES:
            return 0.0
        per_start = self.workloads["ip_per_start"]
        ip = per_start["intercept"] + per_start["per_stamina"] * stamina
        for event, per in per_start.get("per_rate", {}).items():
            ip += per * ((rates or per_start["rates_at"])[event] - per_start["rates_at"][event])
        return self.workloads["starts"] * ip

    def leverage(self, rp_index):
        m = self.leverage_map
        return np.interp(rp_index, m["runs_index"], m["leverage"])

    def starting(self, era, innings) -> dict:
        p = self.pitcher["sp"]
        return {
            "runs": p["per_run"] * (self.pitcher["league_era"] - era) * innings / 9,
            "innings": p["per_nine"] * innings / 9,
        }

    def relieving(self, era, rp_index) -> dict:
        p, innings = self.pitcher["rp"], self.workloads["reliever_ip"]
        runs = p["per_run"] * (self.pitcher["league_era"] - era) * innings / 9
        return {
            "runs": runs,
            "leverage": runs * LEVERAGE_WEIGHT * (self.leverage(rp_index) - 1),
            "innings": p["per_nine"] * innings / 9,
        }


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> ValueModel:
    return ValueModel.from_file(ARTIFACTS_DIR / f"{name}.json")
