"""The baserunning talent model: Speed, Stealing and Baserunning -> runs per 600
PA, under optimal managing (decided 2026-11-08).

    extra bases   UBR (taking the extra base, not getting thrown out) from
                  Speed and Baserunning. Slow runners lose runs here.
    steals        success rate from Stealing, times the attempt rate the most
                  aggressive teams use for that grade (they lose no success
                  rate for it), valued +0.2 a steal / -0.4 caught. Floored at
                  0: a good manager doesn't send a runner below break-even.

Tables are fit at MLB by ranking.fitting.running_talent.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking.hitter_talent import ARTIFACTS_DIR, HIGH, LOW

ARTIFACT = "running_talent_v1"
RATINGS = ("speed", "steal", "running_ability")
SB_RUNS, CS_RUNS = 0.2, -0.4


def _at(table, values):
    return np.asarray(table)[np.clip(np.asarray(values, dtype=int), LOW, HIGH) - LOW]


class RunningTalent:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.extra_bases = artifact["extra_bases"]
        self.steal_success = artifact["steal_success"]
        self.steal_attempts = artifact["steal_attempts"]
        self.times_on_first = artifact["times_on_first"]

    @classmethod
    def from_file(cls, path) -> "RunningTalent":
        return cls(json.loads(Path(path).read_text()))

    def extra_base_runs(self, ratings: dict):
        t = self.extra_bases
        return t["base"] + _at(t["speed"], ratings["speed"]) + _at(t["running_ability"], ratings["running_ability"])

    def steal_runs(self, ratings: dict):
        success = _at(self.steal_success, ratings["steal"])
        per_attempt = success * SB_RUNS + (1 - success) * CS_RUNS
        attempts = _at(self.steal_attempts, ratings["steal"]) * self.times_on_first
        return np.maximum(per_attempt, 0.0) * attempts

    def runs(self, ratings: dict):
        return self.extra_base_runs(ratings) + self.steal_runs(ratings)


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> RunningTalent:
    return RunningTalent.from_file(ARTIFACTS_DIR / f"{name}.json")
