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
STARTER_MIN_STAMINA = 35   # borderline, at the bottom of the innings curve
STARTER_MIN_PITCHES = 3
DISPLAY_OFFSET, DISPLAY_SCALE = 50.0, 10.0
# legacy modifiers the hitter platoons (ranking/stages/value.py) replace
PLATOON_REPLACES = ("BatterHandednessModifier",)


def points(war):
    return DISPLAY_OFFSET + DISPLAY_SCALE * np.asarray(war)


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

    def starter_innings(self, stamina, pitches) -> float:
        """A full-time starter's innings, or 0 when he can't start."""
        if stamina < STARTER_MIN_STAMINA or pitches < STARTER_MIN_PITCHES:
            return 0.0
        per_start = self.workloads["ip_per_start"]
        return self.workloads["starts"] * (per_start["intercept"] + per_start["per_stamina"] * stamina)

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
