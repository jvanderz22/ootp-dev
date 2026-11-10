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

Current ratings come with platoon splits in a league snapshot. A hitter who
has them is scored on each side's events, blended at the share of PA his
batting hand takes against left-handed pitchers (`platoon_mix`); OOTP's
combined ratings are about that blend already, so this mostly stops the
rounded combined rating from hiding a weak side. A hitter without splits
(potential ratings, draft classes) gets the expected ones for his batting hand
and rating level (`expected_sides`); his vs-L / vs-R wRC+ is what the value
layer platoons him on.

Everything is a lookup table per rating (20-80) in a committed artifact, fit by
`ranking.fitting.hitter_talent`; nothing trains at runtime.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT = "hitter_talent_v1"

# component -> the rating that drives it
COMPONENTS = {"k": "avoid_k", "bb": "eye", "hr": "power", "hit": "babip", "xbh": "gap"}
RATINGS = ("babip", "avoid_k", "gap", "power", "eye")
LOW, HIGH = 20, 80
STEPS = np.arange(LOW, HIGH + 1, 5)


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
        # {"R" | "L" | "S": share of PA against left-handed pitchers}
        self.platoon_mix = artifact.get("platoon_mix")
        # {hand: {rating: {"weight": on vL, "gap": [vL - vR at 50, per point]}}}
        self.expected = artifact.get("expected_splits")

    @classmethod
    def from_file(cls, path) -> "HitterTalent":
        return cls(json.loads(Path(path).read_text()))

    def rates(self, ratings: dict) -> dict:
        """Component rates for `ratings` ({rating: number or array}), clamped to
        20-80. OOTP shows ratings in steps of 5 and the tables hold one value
        per step, so a rating between steps (an expected split) reads along
        the line between the two steps around it."""
        out = {}
        for name, rating in COMPONENTS.items():
            value = np.clip(np.asarray(ratings[rating], dtype=float), LOW, HIGH)
            out[name] = np.interp(value, STEPS, self.tables[name][STEPS - LOW])
        return out

    def events(self, ratings: dict) -> dict:
        r = self.rates(ratings)
        return outcomes(r["k"], r["bb"], r["hr"], r["hit"], r["xbh"], self.triple_share)

    def lhp_share(self, bats):
        """The share of PA against left-handed pitchers, per batting hand
        ("R" / "L" / "S")."""
        return np.array([self.platoon_mix[b] for b in bats])

    def platoon_events(self, sides: dict, lhp_share) -> dict:
        """Events against a season's pitchers: `sides` {"vL" | "vR": ratings}
        scored apart and blended at `lhp_share`."""
        vl, vr = self.events(sides["vL"]), self.events(sides["vR"])
        return {k: lhp_share * vl[k] + (1 - lhp_share) * vr[k] for k in vl}

    def expected_sides(self, ratings: dict, bats) -> dict:
        """{"vL" | "vR": ratings} expected from combined `ratings` for hitters
        batting `bats`: the combined rating is OOTP's weighted blend of the two,
        and the gap between them grows with the rating."""
        out = {"vL": {}, "vR": {}}
        for rating in RATINGS:
            c = np.asarray(ratings[rating], dtype=float)
            fit = [self.expected[b][rating] for b in bats]
            weight = np.array([f["weight"] for f in fit])
            gap = np.array([f["gap"][0] for f in fit]) + np.array([f["gap"][1] for f in fit]) * (c - 50)
            out["vL"][rating] = c + (1 - weight) * gap
            out["vR"][rating] = c - weight * gap
        return out

    def wrc_plus(self, ratings: dict):
        return self.wrc_of(self.events(ratings))

    def wrc_of(self, events: dict):
        return 100 * runs_per_pa(events, self.weights) / self.mlb_runs_per_pa


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> HitterTalent:
    return HitterTalent.from_file(ARTIFACTS_DIR / f"{name}.json")
