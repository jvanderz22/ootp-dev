"""The draft odds - the chance he gets there (plans/draft-odds-plan.md): how
much of his ceiling a draftee like him realizes, fit on the league's past
classes (ranking/fitting/draft_odds.py).

His ceiling is his potential ratings' WAR in a full-time role (the draft
profile's model lines). What he's expected to realize is a Poisson fit on the
past classes' value now: the ceiling's base rate, then a factor each for how
developed he already is (readiness: his current ratings' full-time WAR - a
hitter's bat lines alone, 2026-11-20, since his glove is at its ceiling), his
age, his role and his makeup (tapered by the ceiling, as ranking/development.py
tapers it). His age is his draft age - on May 1 of the draft year, from his
date of birth - blended between the fit's age knots, so a player who's nearly
22 reads mostly as a 22 (decided 2026-11-11). Readiness weighs by age, more
from 21 on; and a draftee near MLB-ready from 21 on keeps only half the
penalty of his age from 21.5 to 22 (the "polish" judgment, 2026-11-11: the
value of a player close to the majors right after the draft). Part of that expectation is the chance he outgrows his ceiling:
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
from collections import Counter
from datetime import date
from functools import lru_cache

import numpy as np
from scipy import special, stats

from ranking import development, playing_time
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "draft_odds_v1"
# (lowest bottom of his range, factor), checked from the top; below the last
# step he's x1.00
VELOCITY_STEPS = ((100, 1.15), (98, 1.12), (96, 1.10), (94, 1.05))
# judgment (2026-11-21, you): the share of a hitter's glove (fielding and
# utility at potential, when worth anything) his odds work from. The bat has
# the range of outcomes; a glove is static and pays only if the bat gets him
# on the field. On the past classes' MLB WAR to 26, glove-first ceilings
# (45%+ glove) realized 0.77 of predicted and catchers 0.66, against 1.42 for
# bats with a little glove; at half, 1.07 and 0.71. Interim, until the
# ceiling is split into bat and glove (plans/draft-glove-plan.md)
GLOVE_WEIGHT = 0.5
# judgment (2026-11-21, you): a soft cap on the share of his ceiling a
# draftee is expected to realize, folded into his base rate. Each factor is
# calibrated alone, but stacked they overshoot: held out, draftees predicted
# to realize 50%+ of their ceiling realized 0.64 (value now) / 0.73 (MLB WAR
# to 26) of it, 70%+ 0.38 / 0.67 - mostly high work ethic on a modest
# ceiling (WBF 2122's Nakasone, 89% of 2.62). At 0.8, MLB WAR to 26's top 25
# went 4.80 -> 4.86 and top 50 3.52 -> 3.65; tighter helped no further
SHARE_CAP = 0.8


def realistic(value, ceiling):
    """`value` (a number or an array) with the share of `ceiling` (at least
    MIN_SHARE_CEILING) it comes to softly capped at SHARE_CAP: s / sqrt(1 +
    (s / SHARE_CAP)^2). A typical draftee's 30% stays near 28%; 89% comes to
    60%. Unchanged at or below 0."""
    c = np.maximum(ceiling, MIN_SHARE_CEILING)
    share = np.asarray(value, dtype=float) / c
    capped = c * share / np.sqrt(1 + (share / SHARE_CAP) ** 2)
    out = np.where(share > 0, capped, value)
    return float(out) if np.ndim(out) == 0 else out


MIN_SHARE_CEILING = 0.5
# judgment (2026-11-21, you): the board ranks on his value with a little
# weight on his ceiling - value^(1-w) x ceiling^w - so a high ceiling counts
# for something past what it's expected to return (WBF 2122's Figueroa, POT
# 80 at 17, 8 -> 5; Nakasone, a modest bat, 11 -> 14). Held out on MLB WAR
# to 26: top 10 rose (6.06 -> 6.22 at 0.1), the rest slipped a little (top
# 25 4.86 -> 4.81 at 0.1, 4.61 at 0.2)
UPSIDE_WEIGHT = 0.15


def upside(value, ceiling, reference=1.0):
    """The "Upside" factor on a value: (ceiling / value / `reference`) ^
    UPSIDE_WEIGHT, the ceiling at least MIN_SHARE_CEILING, so his value comes
    to value^(1-w) x ceiling^w over `reference`^w; `reference` is a typical
    draftee's ceiling over his value, so he stays near x1. 1 at or below 0."""
    v = np.asarray(value, dtype=float)
    ratio = np.maximum(ceiling, MIN_SHARE_CEILING) / np.maximum(v, 1e-9) / reference
    out = np.where(v > 0, ratio ** UPSIDE_WEIGHT, 1.0)
    return float(out) if np.ndim(out) == 0 else out
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
    "work_ethic": {"H": "Work ethic", "L": "Work ethic"},
    "intelligence": {"H": "Intelligence", "L": "Intelligence"},
    "injury_prone": {"Fragile": "Fragile", "Wrecked": "Wrecked", "Durable": "Durable", "Iron Man": "Iron Man"},
}
# the share of his E[v] the rest keeps at least, where outgrowing is worth
# nearly all of it
REST_FLOOR = 0.05
# how far past his ceiling the card lets a draftee land without outgrowing
# it (WAR; 2026-11-21). Cut off at the ceiling itself, the range ran tight
# (13% of past draftees above P90, 12% of the top 100, against 10%); at 0.5
# it's as calibrated as before (12%, 9%) and a modest ceiling bounds it
SHORT_REACH = 0.5


def _truncated_theta(mean, k, bound):
    """The gamma scale whose shape-`k` gamma, cut off at `bound`, has mean
    `mean` (arrays or numbers). Its mean rises with the scale toward
    bound x k / (k + 1); a mean past that takes the largest scale tried."""
    mean, k, bound = np.broadcast_arrays(np.asarray(mean, float), np.asarray(k, float), np.asarray(bound, float))
    lo, hi = np.full(mean.shape, 1e-6), np.maximum(bound, 1e-6) * 1e3

    def cut_mean(theta):
        return k * theta * special.gammainc(k + 1, bound / theta) / np.maximum(special.gammainc(k, bound / theta), 1e-300)
    for _ in range(40):
        mid = np.sqrt(lo * hi)
        low = cut_mean(mid) < mean
        lo, hi = np.where(low, mid, lo), np.where(low, hi, mid)
    return np.sqrt(lo * hi)


def card(expected, q, p, k, ceiling, margin, excess) -> dict:
    """The card's three outcomes (2026-11-21), in WAR: he outgrows his ceiling
    (chance `q`: past it by `margin` and then a gamma, `excess` its (shape,
    scale)); or he doesn't, and busts (0, chance 1 - `p`) or lands short of
    it - a shape-`k` gamma cut off SHORT_REACH past his `ceiling`, its mean
    set so the whole comes to `expected`. Arrays or numbers; read with `card_cdf` and
    `card_quantile`."""
    shape, scale = excess
    expected, q, p, k, ceiling = (np.asarray(x, float) for x in (expected, q, p, k, ceiling))
    bound = np.maximum(ceiling, MIN_SHARE_CEILING) + SHORT_REACH
    worth = np.maximum(ceiling, MIN_SHARE_CEILING) + margin + shape * scale
    rest = np.maximum((expected - q * worth) / (1 - q), REST_FLOOR * expected)
    # a value near his ceiling can't come from a spread cut off there and his
    # bust chance both: the most a cut-off gamma averages is bound x k / (k +
    # 1), so past that he busts less, as often as the mean needs
    most = 0.98 * bound * k / (k + 1)
    p = np.clip(np.maximum(p, rest / most), 0.0, 1.0)
    theta = _truncated_theta(np.minimum(rest / p, most), k, bound)
    return {"q": q, "p": p, "k": k, "theta": theta, "bound": bound, "norm": special.gammainc(k, bound / theta),
            "floor": np.maximum(ceiling, MIN_SHARE_CEILING) + margin, "excess": (shape, scale)}


def card_cdf(v, c: dict):
    """P(his value <= `v`) on `card`'s outcomes."""
    v = np.asarray(v, float)
    short = (1 - c["p"]) + c["p"] * np.minimum(special.gammainc(c["k"], np.maximum(v, 0) / c["theta"]) / c["norm"], 1.0)
    grown = special.gammainc(c["excess"][0], np.maximum(v - c["floor"], 0) / c["excess"][1])
    return np.where(v < 0, 0.0, (1 - c["q"]) * short + c["q"] * grown)


def card_quantile(level, c: dict, top=40.0):
    """The `level` quantile of `card`'s outcomes, in WAR (0 when the bust
    alone reaches it)."""
    lo = np.zeros(np.shape(c["theta"]))
    hi = lo + top
    for _ in range(32):
        mid = (lo + hi) / 2
        below = card_cdf(mid, c) < level
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
    out = np.where(card_cdf(np.zeros_like(lo), c) >= level, 0.0, hi)
    return float(out) if np.ndim(out) == 0 else out


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


# the draft age: his age on this day of the draft year, from his date of birth
# (decided 2026-11-11). The exports' Age is as of whenever they were pulled,
# late April to June; May 1 is the nearest to most of them
AGE_DATE = (5, 1)


def draft_year(players):
    """The year an export was pulled in, read off it: birth year plus Age for
    the players born in January or February, whose birthday has passed by any
    spring export. None without dates of birth."""
    years = Counter(p.birth_date.year + p.age for p in players if p.birth_date and p.birth_date.month <= 2)
    return years.most_common(1)[0][0] if years else None


def draft_age(player, year) -> float:
    """His age on AGE_DATE of the draft `year`, in years; the export's Age +
    0.5 without a date of birth or a year."""
    if player.birth_date is None or year is None:
        return player.age + 0.5
    return (date(year, *AGE_DATE) - player.birth_date).days / 365.2425


def knot_weights(age, knots) -> dict:
    """{knot: weight}: `age` (a number or an array) shared linearly between
    the two knots around it, held at the end knots."""
    a = np.clip(np.asarray(age, dtype=float), knots[0], knots[-1])
    out = {}
    for i, k in enumerate(knots):
        w = np.zeros_like(a)
        if i:
            lo = knots[i - 1]
            w = np.where((a >= lo) & (a <= k), (a - lo) / (k - lo), w)
        if i + 1 < len(knots):
            hi = knots[i + 1]
            w = np.where((a >= k) & (a <= hi), (hi - a) / (hi - k), w)
        out[k] = w
    return out


def pitcher_ease(readiness, judgment):
    """The share of the pitcher polish a pitcher of `readiness` WAR now (a
    number or an array) gets: his percentile among 22-year-old pitchers, read
    off `judgment`'s (WAR now, percentile) knots, 0 at `none`, 1 from `full`."""
    war, pct = zip(*judgment["percentiles"])
    at = np.interp(readiness, war, pct)
    return np.clip((at - judgment["none"]) / (judgment["full"] - judgment["none"]), 0.0, 1.0)


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
        self.ramp = artifact.get("pitcher_ramp", {"ramp": 0.0, "war": 1.0})
        self.plays = playing_time.PlayingTime.of(artifact)
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

    def ages(self, age) -> dict:
        """{label: weight} of a draft age on the fit's age knots, the
        reference left out."""
        a = self.a["age"]
        weights = knot_weights(age, a["knots"])
        return {f"{k:g}": float(weights[k]) for k in a["knots"] if k != a["reference"]}

    def mean_columns(self, player, ceiling, readiness, group, age) -> dict:
        """The Poisson fit's columns (ranking/fitting/draft_odds.py's
        `design`) for one side of him, `age` his draft age."""
        lp, taper = self.log_potential(ceiling), development.weight(ceiling)
        cols = {"log potential": lp, "readiness": self.readiness(readiness),
                "SP": float(group == "SP"), "RP": float(group == "RP")}
        ages = self.ages(age)
        for label, w in ages.items():
            cols[f"age {label}"] = w
        for label, w in ages.items():
            cols[f"age {label} x potential"] = lp * w
        for label, w in ages.items():
            cols[f"readiness x age {label}"] = cols["readiness"] * w
        for label, (attr, values) in MAKEUP.items():
            cols[label] = float(getattr(player, attr) in values) * taper
        return cols

    def growth_columns(self, player, ceiling, readiness, group, pitches, age) -> dict:
        """The growth odds' columns (`growth_design`), read at the reference
        years after the draft; `age` his draft age, in whole years here."""
        age, pitcher = int(np.floor(age)), float(group != "hitter")
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

    def expected(self, cols, age) -> float:
        """The Poisson mean: base x (ceiling / reference) ^ exponent x the
        factors, with the polish judgment for a draftee of draft age `age`."""
        z = self._mean_logit(cols)
        return float(np.exp(z + self.polish(cols, age, self.penalty(cols["log potential"], self._mean_age))))

    def polish(self, cols, age, penalty) -> float:
        """The logit the polish judgment (the artifact's) adds back: its share
        of `penalty` - none at `from` WAR now, `share` from `full` up - for a
        draft age past `eligible`'s start, in full past its end."""
        p = self.a["judgment"]["polish"]
        lo, hi = p["eligible"]
        eligible = np.clip((age - lo) / (hi - lo), 0.0, 1.0)
        ready = np.clip((cols["readiness"] - p["from"]) / (p["full"] - p["from"]), 0.0, 1.0)
        return float(-p["share"] * ready * eligible * min(penalty, 0.0)) + self.pitcher_polish(cols)

    def pitcher_polish(self, cols) -> float:
        """The logit the pitcher polish judgment (the artifact's, 2026-11-21)
        adds: a pitcher's 22 age factor eased toward its `age_22_factor` by
        his weight on the 22 knot and how advanced he is for a 22-year-old
        pitcher - his percentile of WAR now among them, none at `none`, in
        full from `full` up. 0 for a hitter, and without the judgment."""
        p = self.a["judgment"].get("pitcher_polish")
        if not p or not (cols["SP"] or cols["RP"]):
            return 0.0
        ease = pitcher_ease(cols["readiness"], p)
        return float(ease * cols["age 22"] * np.log(p["age_22_factor"] / self.a["age"]["factor"]["22"]))

    def penalty(self, lp, at) -> float:
        """The age logit's drop between the polish judgment's `eased` ages at
        log potential `lp`; `at(label)` is a knot's (logit, potential tilt)."""
        lo, hi = self.a["judgment"]["polish"]["eased"]

        def logit(age):
            return sum(w * (at(label)[0] + at(label)[1] * lp) for label, w in self.ages(age).items())
        return float(logit(hi) - logit(lo))

    def _mean_age(self, label) -> tuple:
        a = self.a["age"]
        return np.log(a["factor"][label]), a["by_potential"][label]

    def _age_logit(self, cols) -> float:
        a = self.a["age"]
        return sum(np.log(a["factor"][label]) * cols[f"age {label}"] + a["by_potential"][label] * cols[f"age {label} x potential"]
                   for label in a["factor"])

    def _mean_logit(self, cols) -> float:
        a = self.a
        z = np.log(a["base"]) + a["potential_exponent"] * cols["log potential"]
        z += np.log(a["readiness"]["per_war"]) * cols["readiness"]
        z += sum(np.log(f) * cols[f"readiness x age {label}"] for label, f in a["readiness"]["by_age"].items())
        z += self._age_logit(cols)
        z += sum(np.log(a["role"][g]) * cols[g] for g in ("SP", "RP"))
        z += sum(np.log(f) * cols[label] for label, f in a["makeup"].items())
        return z

    def pitcher_balance(self, war) -> float:
        """The hitter-pitcher balance on a pitcher worth `war` before it:
        the factor, ramped by his value (2026-11-21), so the best pitchers
        are lifted more and every rank bucket sits near 50/50."""
        r = self.ramp
        return float(self.balance * (max(war, 1e-6) / r["war"]) ** r["ramp"])

    def playing(self, bat, bat_now, glove, run, age, catcher=False) -> float:
        """The playing-time factor (ranking/playing_time.py) for a draftee:
        on his bat's ceiling and WAR now, his glove and run at potential and
        his draft age. 1 without the fit, and for a catcher."""
        if self.plays is None:
            return 1.0
        cols = {"bat": bat, "bat now": float(np.clip(bat_now, *self.plays.block["clip"])), "glove": glove, "run": run,
                **{f"age {label}": w for label, w in self.ages(age).items()}, playing_time.CATCHER: float(catcher)}
        return self.plays.factor(cols, catcher)

    def outgrows(self, growth_cols) -> float:
        g = self.growth
        z = g["intercept"] + g["realized_shift"] + sum(c * growth_cols[n] for n, c in g["coef"].items())
        return float(1 / (1 + np.exp(-z)))

    def outgrown_worth(self, ceiling) -> float:
        """What outgrowing his ceiling is worth on average: past it by the
        margin, and then some."""
        shape, scale = self.excess
        return ceiling + self.margin + shape * scale

    def reaching(self, player, ceiling, readiness, group, growth_cols, age, switch=None) -> tuple:
        """(ledger lines, E[v]) for one side: lines are (kind, label, value,
        stat, note), kind "add" (value in WAR) or "scale" (value a factor),
        from his ceiling to what he's expected to realize; `age` his draft
        age. `switch` is the switch hitter's (label, factor, note), applied
        with the factors."""
        a, cols = self.a, self.mean_columns(player, ceiling, readiness, group, age)
        expected = self.expected(cols, age)
        q = self.outgrows(growth_cols)
        rest = max((expected - q * self.outgrown_worth(ceiling)) / (1 - q), REST_FLOOR * expected)
        growth = expected - rest
        reference = float(np.exp(np.log(a["base"]) + a["potential_exponent"] * cols["log potential"]))
        base = reference * (1 - growth / expected)
        share = f"{reference / ceiling:.0%}" if ceiling > a["log_floor"] else f"{reference:.2f} WAR"
        lines = [("add", "Base rate", base - ceiling, share, None)]
        by_age = np.prod([f ** cols[f"readiness x age {label}"] for label, f in a["readiness"]["by_age"].items()])
        lines.append(("scale", "Readiness", a["readiness"]["per_war"] ** cols["readiness"] * by_age, None,
                      f"{readiness:+.1f} WAR now"))
        logit = self._age_logit(cols)
        if logit:
            lines.append(("scale", f"Age {age:.1f}", float(np.exp(logit)), None, None))
        eased = self.polish(cols, age, self.penalty(cols["log potential"], self._mean_age))
        if eased:
            lines.append(("scale", "Polish", float(np.exp(eased)), None, None))
        if group == "SP":
            lines.append(("scale", "Starter", a["role"]["SP"], None, None))
        elif group == "RP":
            lines.append(("scale", "Reliever", a["role"]["RP"], None, None))
        taper = development.weight(ceiling)
        for label, (attr, values) in MAKEUP.items():
            value = getattr(player, attr)
            if value in values:
                lines.append(("scale", MAKEUP_LABELS[attr][value], a["makeup"][label] ** taper, None, None))
        factor = 1.0
        if switch:
            lines.append(("scale", "Switch hitter", switch[1], None, None))
            factor = switch[1]
        lines.append(("add", "Breakout", growth * factor, f"{q:.0%}", self._growth_note(player, growth_cols, age)))
        return lines, expected * factor

    def _growth_note(self, player, cols, age) -> str:
        """What lifts his chance of outgrowing his ceiling, in a few words."""
        out = []
        if cols["age 19-"]:
            out.append(f"age {int(np.floor(age))}")
        if cols["velocity"] >= 3 and self.growth["coef"]["velocity"] > 0:
            out.append(f"{_top_velocity(player.velocity):.0f} mph")
        if cols["WE H"]:
            out.append("work ethic")
        if cols["AD H"]:
            out.append("adaptability")
        return ", ".join(out) or None

    # -- the card's distribution -----------------------------------------------

    def distribution(self, cols, growth_cols, ceiling, group, expected, scale, age) -> dict:
        """The likely range (P10, P90), the chance he becomes a regular and the
        chance he outgrows his ceiling, for a side whose odds come to
        `expected` WAR and whose value before the board's ranking judgments
        (the pitcher balance, Upside) is `scale` x that, with his whole
        `ceiling`. In real WAR (2026-11-21): short of outgrowing he lands at
        most SHORT_REACH past his ceiling, and outgrowing is past it by the
        margin."""
        q = self.outgrows(growth_cols)
        coef = self.sticks["coef"]
        z = self.sticks["intercept"] + sum(c * cols[n] for n, c in coef.items())
        at = lambda label: (coef[f"age {label}"], coef[f"age {label} x potential"])   # noqa: E731
        z += self.polish(cols, age, self.penalty(cols["log potential"], at))
        p = 1 / (1 + np.exp(-z))
        c = card(expected * scale, q, p, self.shape[group], ceiling, self.margin, self.excess)
        return {"p10": card_quantile(0.1, c), "p90": card_quantile(0.9, c),
                "regular": float(1 - card_cdf(self.regular[group], c)), "outgrows": q}


@lru_cache(maxsize=None)
def load(name: str = ARTIFACT) -> DraftOdds:
    return DraftOdds.from_file(ARTIFACTS_DIR / f"{name}.json")

