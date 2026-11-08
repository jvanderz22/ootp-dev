"""The pitcher talent model: base pitching ratings -> expected MLB rates -> runs
allowed, as a starter and as a reliever.

Each rating drives one rate per batter faced, the mirror of the hitters':

    k     strikeouts per BF                   Stuff
    bb    unintentional walks + HBP per BF    Control
    hr    home runs per contact               HRA
    hit   non-HR hits per ball in play        PBABIP

Movement is OOTP's composite of HRA and PBABIP (~0.8 / 0.2), so it isn't read
when they are. Classes exported without HRA / PBABIP (the draft view) use
tables fit on Movement for `hr` and `hit` instead.

Extra-base hits allowed aren't in the stats, so hits split at the MLB rate.
Outcomes are valued with the hitters' linear weights, and runs allowed are an
index: 100 is the MLB average batter's line, lower is better. `era` puts the
same runs per nine innings, scaled so the MLB average line gives the league's
ERA (which takes care of unearned runs and the outs the events leave out).
Starting and relieving differ by a fitted role term, and by Stuff itself: OOTP
shows Stuff for the listed role, weighting a starter's 3rd pitch more and a
reliever's top two (measured 2026-11-08 by exporting one org's pitchers all as
SP and all as RP; nothing else changes). `role_stuff` moves displayed Stuff
into the other role with the fitted shift: a listed starter gains it in relief,
anyone else loses it plus a margin as a starter, erring towards taking too much
away rather than too little.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking import bridge
from ranking.hitter_talent import ARTIFACTS_DIR, HIGH, LOW, outcomes, runs_per_pa

ARTIFACT = "pitcher_talent_v1"

COMPONENTS = {"k": "stuff", "bb": "control", "hr": "hra", "hit": "pbabip"}
MOVEMENT_COMPONENTS = {"hr": "movement", "hit": "movement"}
RATINGS = ("stuff", "control", "hra", "pbabip", "movement")
ROLES = ("sp", "rp")
# pitches the role shift reads, best first
SHIFT_PITCHES = 4


def top_pitches(grades) -> list:
    """The best SHIFT_PITCHES grades, best first, 0 for a pitch he lacks."""
    top = sorted((g for g in grades if g), reverse=True)[:SHIFT_PITCHES]
    return top + [0] * (SHIFT_PITCHES - len(top))


class PitcherTalent:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.tables = {
            role: {name: np.asarray(t) for name, t in tables.items()}
            for role, tables in artifact["tables"].items()
        }
        self.movement_tables = {
            role: {name: np.asarray(t) for name, t in tables.items()}
            for role, tables in artifact["movement_tables"].items()
        }
        self.weights = artifact["linear_weights"]
        self.extra_base_share = artifact["extra_base_share"]
        self.triple_share = artifact["triple_share"]
        self.mlb_runs_per_pa = artifact["mlb_runs_per_pa"]
        self.era_scale = artifact.get("era_scale")
        # {"overall" | "potential": {"coef": [intercept, best, 2nd, ...], "margin"}}
        self.role_shift = artifact.get("role_shift")
        # runs allowed index -> legacy SP / RP points (ranking/bridge.py);
        # absent while fitting
        self.bridges = artifact.get("points_bridges")

    @classmethod
    def from_file(cls, path) -> "PitcherTalent":
        return cls(json.loads(Path(path).read_text()))

    def rates(self, ratings: dict, role: str) -> dict:
        """Component rates for `ratings` ({rating: int or array}) in `role`.
        Without `hra` / `pbabip` (None), `hr` and `hit` come from Movement."""
        movement = ratings.get("hra") is None or ratings.get("pbabip") is None
        out = {}
        for name, rating in COMPONENTS.items():
            table = self.tables[role][name]
            if movement and name in MOVEMENT_COMPONENTS:
                rating, table = MOVEMENT_COMPONENTS[name], self.movement_tables[role][name]
            out[name] = table[np.clip(np.asarray(ratings[rating], dtype=int), LOW, HIGH) - LOW]
        return out

    def stuff_shift(self, top, side: str):
        """Stuff gained as a reliever over a starter, from `top` (rows of
        top_pitches) on `side` ("overall" or "potential"); never negative."""
        coef = np.asarray(self.role_shift[side]["coef"])
        return np.maximum(coef[0] + np.asarray(top, dtype=float) @ coef[1:], 0.0)

    def role_stuff(self, stuff, top, listed_sp, side: str) -> dict:
        """{role: Stuff in that role} from displayed Stuff, which is for the
        listed role: a listed SP's as a starter, anyone else's as a reliever."""
        stuff, listed_sp = np.asarray(stuff, dtype=float), np.asarray(listed_sp, dtype=bool)
        shift = self.stuff_shift(top, side)
        margin = self.role_shift[side]["margin"]
        return {
            "sp": np.rint(np.where(listed_sp, stuff, stuff - shift - margin)),
            "rp": np.rint(np.where(listed_sp, stuff + shift, stuff)),
        }

    def events(self, ratings: dict, role: str) -> dict:
        r = self.rates(ratings, role)
        return outcomes(r["k"], r["bb"], r["hr"], r["hit"], self.extra_base_share, self.triple_share)

    def runs_index(self, ratings: dict, role: str):
        return 100 * runs_per_pa(self.events(ratings, role), self.weights) / self.mlb_runs_per_pa

    def era(self, ratings: dict, role: str):
        events = self.events(ratings, role)
        return era_from(events, self.weights, self.era_scale)

    def points(self, runs_index, role: str):
        return bridge.points(runs_index, self.bridges[role])


def era_from(events: dict, weights: dict, scale: float):
    """Runs per nine innings from per-PA events (27 outs: strikeouts and outs in
    play), times `scale`."""
    return scale * 27 * runs_per_pa(events, weights) / (events["k"] + events["out"])


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> PitcherTalent:
    return PitcherTalent.from_file(ARTIFACTS_DIR / f"{name}.json")
