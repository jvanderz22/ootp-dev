"""The hitter talent model: base batting ratings -> expected MLB rates -> runs.

Each rating drives one rate, the way OOTP uses them:

    k     strikeouts per PA                    Avoid K
    bb    unintentional walks + HBP per PA     Eye
    hr    home runs per contact                Power    contact = PA - K - BB - HBP
    hit   non-HR hits per ball in play         BABIP    ball in play = contact - HR
    xbh   doubles + triples per non-HR hit     Gap

The rates chain into a PA's outcomes, so interactions come from the game's own
arithmetic rather than a fitted term: a hitter who strikes out more has fewer
balls for his Power and BABIP to act on. Outcomes are valued with linear
weights fit to the league's team-season runs, and expressed as wRC+ against
the MLB average.

Everything is a lookup table per rating (20-80) in a committed artifact, fit by
`ranking.fitting.hitter_talent`; nothing trains at runtime.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from ranking import bridge

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT = "hitter_talent_v1"

# component -> the rating that drives it
COMPONENTS = {"k": "avoid_k", "bb": "eye", "hr": "power", "hit": "babip", "xbh": "gap"}
RATINGS = ("babip", "avoid_k", "gap", "power", "eye")
LOW, HIGH = 20, 80


def outcomes(k, bb, hr, hit, xbh, triple_share):
    """Per-PA event rates from the five component rates (arrays or floats)."""
    contact = 1 - k - bb
    homers = contact * hr
    in_play = contact - homers
    hits = in_play * hit
    extra = hits * xbh
    return {
        "single": hits - extra,
        "double": extra * (1 - triple_share),
        "triple": extra * triple_share,
        "hr": homers,
        "bb": bb,
        "k": k,
        "out": in_play - hits,
    }


def runs_per_pa(events, weights):
    return sum(events[name] * weights[name] for name in events)


class HitterTalent:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.tables = {name: np.asarray(artifact["tables"][name]) for name in COMPONENTS}
        self.weights = artifact["linear_weights"]
        self.triple_share = artifact["triple_share"]
        self.mlb_runs_per_pa = artifact["mlb_runs_per_pa"]
        # wRC+ -> the legacy batting model's points (ranking/bridge.py); absent
        # while fitting
        self.bridge = artifact.get("points_bridge")

    @classmethod
    def from_file(cls, path) -> "HitterTalent":
        return cls(json.loads(Path(path).read_text()))

    def rates(self, ratings: dict) -> dict:
        """Component rates for `ratings` ({rating: int or array}), clamped to 20-80."""
        out = {}
        for name, rating in COMPONENTS.items():
            index = np.clip(np.asarray(ratings[rating], dtype=int), LOW, HIGH) - LOW
            out[name] = self.tables[name][index]
        return out

    def wrc_plus(self, ratings: dict):
        r = self.rates(ratings)
        events = outcomes(r["k"], r["bb"], r["hr"], r["hit"], r["xbh"], self.triple_share)
        return 100 * runs_per_pa(events, self.weights) / self.mlb_runs_per_pa

    def points(self, wrc_plus):
        return bridge.points(wrc_plus, self.bridge)


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> HitterTalent:
    return HitterTalent.from_file(ARTIFACTS_DIR / f"{name}.json")
