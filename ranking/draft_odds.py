"""The draft odds - the chance he gets there (plans/draft-odds-plan.md): how
much of his ceiling a draftee like him realizes, fit on the league's past
classes (ranking/fitting/draft_odds.py).

His ceiling is his potential ratings' WAR in a full-time role (the draft
profile's model lines). What he's expected to realize is a Poisson fit on the
past classes' value now: the ceiling's base rate, then a factor each for how
developed he already is (readiness: his current ratings' full-time WAR), his
age, his role and his makeup (tapered by the ceiling, as ranking/development.py
tapers it). Part of that expectation is the chance he outgrows his ceiling:
the growth odds (fit on the ceiling panel, with your work ethic and velocity
judgment) and what outgrowing is worth. On the ledger the factors scale the
rest, and the growth is its own line, so the lines sum to the expectation.

The same fit gives the card its distribution: the bust, short-of-ceiling and
outgrown outcomes, with the rest's mean set so the whole matches the board's
expectation. From it, the likely range (P10-P90), the chance he becomes a
regular and the chance he outgrows his ceiling.

Velocity (decided 2026-11-10, open question 4): an upside, never a penalty.
Held out on the past classes, with the odds' mean held fixed, pitchers whose
range topped out at 96-97 realized about 16% more than predicted and at 98-99
about 59% (36 pitchers); slower arms realized at least what was predicted.
The steps take about half of that, by the bottom of his range, as legacy's
PitcherVelocityModifier reads it. Stuff gets no line: the low end beat the
odds and the high end added nothing, so its legacy cuts are dropped.
"""
import json
import re
from functools import lru_cache

import numpy as np
from scipy import stats

from ranking import development
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "draft_odds_v1"
# (lowest bottom of his range, factor), checked from the top; below the last
# step he's x1.00
VELOCITY_STEPS = ((100, 1.15), (98, 1.12), (96, 1.10), (94, 1.05))
# the legacy modifiers the odds replace on the draft board, and the two
# judgment lines replaced here: velocity by `velocity_factor`, Stuff by nothing
REPLACES = (
    "AgeModifier", "DraftBatterOverallModifier", "DraftPitcherOverallModifier",
    "DraftPitcherStuffModifier", "PitcherVelocityModifier",
)
# the makeup the fit reads: {column: (GamePlayer attribute, values)}
MAKEUP = {
    "WE H": ("work_ethic", ("H",)), "WE L": ("work_ethic", ("L",)),
    "INT H": ("intelligence", ("H",)), "INT L": ("intelligence", ("L",)),
    "fragile": ("injury_prone", ("Fragile", "Wrecked")), "durable": ("injury_prone", ("Durable", "Iron Man")),
}
GROWTH_ONLY = {"AD H": ("adaptibility", ("H",)), "AD L": ("adaptibility", ("L",))}
# the card's labels for the makeup lines, by the rating's value
MAKEUP_LABELS = {
    "work_ethic": {"H": "High work ethic", "L": "Low work ethic"},
    "intelligence": {"H": "High intelligence", "L": "Low intelligence"},
    "injury_prone": {"Fragile": "Injury-prone", "Wrecked": "Very injury-prone",
                     "Durable": "Durable", "Iron Man": "Very durable"},
}
# the share of his E[v] the rest keeps at least, where outgrowing is worth
# nearly all of it
REST_FLOOR = 0.05


def velocity_factor(velocity, knuckleball=False) -> float:
    """The upside his velocity range ("94-96") earns; 1 for a knuckleballer,
    or with no range exported."""
    found = re.search(r"\d+", str(velocity or ""))
    if knuckleball or not found:
        return 1.0
    bottom = int(found[0])
    return next((factor for low, factor in VELOCITY_STEPS if bottom >= low), 1.0)


def _top_velocity(velocity) -> float:
    found = re.findall(r"\d+", str(velocity or ""))
    return float(found[-1]) if found else np.nan


def _number(value, default) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class DraftOdds:
    def __init__(self, artifact: dict):
        self.version = artifact["version"]
        self.a = artifact
        self.regular = artifact["regular"]
        self.balance = artifact["pitcher_balance"]
        dist = artifact["distribution"]
        self.growth = dist["growth"]
        self.sticks = dist["sticks"]
        self.excess = dist["outgrown"]["excess_gamma"]
        self.margin = dist["outgrown"]["margin"]
        self.shape = dist["gamma_shape"]

    @classmethod
    def from_file(cls, path) -> "DraftOdds":
        return cls(json.loads(path.read_text()))

    # -- the fit's columns ------------------------------------------------------

    def log_potential(self, ceiling) -> float:
        return float(np.log(max(ceiling, self.a["log_floor"]) / self.a["reference_war"]))

    def readiness(self, readiness) -> float:
        return float(np.clip(readiness, *self.a["readiness"]["clip"]))

    def mean_columns(self, player, ceiling, readiness, group) -> dict:
        """The Poisson fit's columns (ranking/fitting/draft_odds.py's
        `design`) for one side of him."""
        lp, age, taper = self.log_potential(ceiling), player.age, development.weight(ceiling)
        cols = {"log potential": lp, "readiness": self.readiness(readiness),
                "SP": float(group == "SP"), "RP": float(group == "RP")}
        for label, (lo, hi, _) in self.a["age"].items():
            cols[f"age {label}"] = float(lo <= age <= hi)
        for label, (lo, hi, _) in self.a["age_by_potential"].items():
            cols[f"age {label} x potential"] = lp * (lo <= age <= hi)
        for label, (attr, values) in MAKEUP.items():
            cols[label] = float(getattr(player, attr) in values) * taper
        return cols

    def growth_columns(self, player, ceiling, readiness, group, pitches) -> dict:
        """The growth odds' columns (`growth_design`), read at the reference
        years after the draft."""
        age, pitcher = player.age, float(group != "hitter")
        cols = {"log potential": self.log_potential(ceiling), "readiness": self.readiness(readiness),
                "SP": float(group == "SP"), "RP": float(group == "RP"),
                "age 19-": float(age <= 19), "age 22+": float(age >= 22), "years": 0.0}
        for label, (attr, values) in {**MAKEUP, **GROWTH_ONLY}.items():
            cols[label] = float(getattr(player, attr) in values)
        velo = _top_velocity(player.velocity)
        cols["velocity"] = pitcher * ((93.0 if np.isnan(velo) else velo) - 93)
        cols["Stuff P / 10"] = pitcher * (_number(player.stuff, 45.0) - 45) / 10
        cols["pitches"] = pitcher * (pitches - 3)
        return cols

    # -- what he's expected to realize -----------------------------------------

    def expected(self, cols) -> float:
        """The Poisson mean: base x (ceiling / reference) ^ exponent x the factors."""
        return float(np.exp(self._mean_logit(cols)))

    def _mean_logit(self, cols) -> float:
        a = self.a
        z = np.log(a["base"]) + a["potential_exponent"] * cols["log potential"]
        z += np.log(a["readiness"]["per_war"]) * cols["readiness"]
        z += sum(np.log(a["role"][g]) * cols[g] for g in ("SP", "RP"))
        z += sum(np.log(f) * cols[f"age {label}"] for label, (_, _, f) in a["age"].items())
        z += sum(e * cols[f"age {label} x potential"] for label, (_, _, e) in a["age_by_potential"].items())
        z += sum(np.log(f) * cols[label] for label, f in a["makeup"].items())
        return z

    def outgrows(self, growth_cols) -> float:
        g = self.growth
        z = g["intercept"] + g["realized_shift"] + sum(c * growth_cols[n] for n, c in g["coef"].items())
        return float(1 / (1 + np.exp(-z)))

    def outgrown_worth(self, ceiling) -> float:
        """What outgrowing his ceiling is worth on average: past it by the
        margin, and then some."""
        shape, scale = self.excess
        return ceiling + self.margin + shape * scale

    def reaching(self, player, ceiling, readiness, group, growth_cols, switch=None) -> tuple:
        """(ledger lines, E[v]) for one side: lines are (kind, label, value,
        stat, note), kind "add" (value in WAR) or "scale" (value a factor),
        from his ceiling to what he's expected to realize. `switch` is the
        switch hitter's (label, factor, note), applied with the factors."""
        a, cols = self.a, self.mean_columns(player, ceiling, readiness, group)
        expected = self.expected(cols)
        q = self.outgrows(growth_cols)
        rest = max((expected - q * self.outgrown_worth(ceiling)) / (1 - q), REST_FLOOR * expected)
        growth = expected - rest
        reference = float(np.exp(np.log(a["base"]) + a["potential_exponent"] * cols["log potential"]))
        base = reference * (1 - growth / expected)
        share = f"reach {reference / ceiling:.0%} of it" if ceiling > a["log_floor"] else f"{reference:.2f} WAR"
        lines = [("add", "Draftees with his ceiling", base - ceiling, share, "at 21, with average makeup")]
        r = cols["readiness"]
        lines.append(("scale", "How developed he is", a["readiness"]["per_war"] ** r, None,
                      f"{readiness:+.1f} WAR on today's ratings" + (": a long way to go" if readiness < -1 else "")))
        age = player.age
        for label, (lo, hi, f) in a["age"].items():
            if lo <= age <= hi:
                tilt = next((e for lab, (l2, h2, e) in a["age_by_potential"].items() if l2 <= age <= h2), 0.0)
                young = age < 21
                note = "More time to develop" if young else "Less time to develop"
                if tilt and cols["log potential"] > 0:
                    note += "; counts for less with a ceiling this high" if young else "; costs less with a ceiling this high"
                lines.append(("scale", f"Drafted at {age}", f * np.exp(tilt * cols["log potential"]), None, note))
        if group == "SP":
            lines.append(("scale", "Starters often end up relieving", a["role"]["SP"], None,
                          "Most drafted starters don't stay in a rotation"))
        elif group == "RP":
            lines.append(("scale", "Drafted as a reliever", a["role"]["RP"], None, "Relievers reach the majors more often"))
        taper = development.weight(ceiling)
        for label, (attr, values) in MAKEUP.items():
            value = getattr(player, attr)
            if value in values:
                note = f"Counts for less with a ceiling this high ({taper:.0%})" if taper < 1 else None
                lines.append(("scale", MAKEUP_LABELS[attr][value], a["makeup"][label] ** taper, None, note))
        factor = 1.0
        if switch:
            lines.append(("scale", "Switch hitter", switch[1], None, "Lets you set the lineup either way"))
            factor = switch[1]
        lines.append(("add", "Could outgrow his ceiling", growth * factor, f"{q:.0%} chance",
                      self._growth_note(player, growth_cols)))
        return lines, expected * factor

    def _growth_note(self, player, cols) -> str:
        """What lifts his chance of outgrowing his ceiling, in words."""
        coef, out = self.growth["coef"], []
        if cols["age 19-"]:
            out.append(f"drafted at {player.age}")
        if cols["velocity"] >= 3 and coef["velocity"] > 0:
            out.append(f"{_top_velocity(player.velocity):.0f} mph")
        if cols["WE H"]:
            out.append("high work ethic")
        if cols["AD H"]:
            out.append("adaptable")
        if cols["RP"]:
            out.append("relievers' ceilings grow most")
        if not out:
            return None
        text = out[0] if len(out) == 1 else ", ".join(out[:-1]) + " and " + out[-1]
        return text[0].upper() + text[1:]

    # -- the card's distribution -----------------------------------------------

    def distribution(self, cols, growth_cols, ceiling, group, expected, scale) -> dict:
        """The likely range (P10, P90), the chance he becomes a regular and the
        chance he outgrows his ceiling, for a side whose odds come to
        `expected` WAR and whose value is `scale` x that."""
        q = self.outgrows(growth_cols)
        z = self.sticks["intercept"] + sum(c * cols[n] for n, c in self.sticks["coef"].items())
        p = 1 / (1 + np.exp(-z))
        rest = max((expected - q * self.outgrown_worth(ceiling)) / (1 - q), REST_FLOOR * expected)
        k = self.shape[group]
        theta = rest / p / k
        floor = ceiling + self.margin
        shape, excess = self.excess

        def cdf(v):   # in the odds' WAR, before `scale`
            if v < 0:
                return 0.0
            short = (1 - p) + p * stats.gamma.cdf(v, k, scale=theta)
            return (1 - q) * short + q * stats.gamma.cdf(v - floor, shape, scale=excess)

        def quantile(level):
            if cdf(0.0) >= level:
                return 0.0
            lo, hi = 0.0, max(40.0, floor + 20 * excess)
            for _ in range(50):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if cdf(mid) < level else (lo, mid)
            return hi

        regular = self.regular[group] / scale if scale > 0 else np.inf
        return {"p10": quantile(0.1) * scale, "p90": quantile(0.9) * scale,
                "regular": 1 - cdf(regular), "outgrows": q}


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> DraftOdds:
    return DraftOdds.from_file(ARTIFACTS_DIR / f"{name}.json")

