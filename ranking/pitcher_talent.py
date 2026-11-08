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
Starting and relieving differ by a fitted role term (relievers strike out
more), not by shifting the ratings.
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
