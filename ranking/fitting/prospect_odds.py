"""Fit the prospect odds - the chance he gets there, for the league's
prospects (plans/prospect-odds-plan.md) - and write their artifact.

    python -m ranking.fitting.prospect_odds --data-dir fly_data [--table prospects.pkl]
    python -m ranking.fitting.prospect_odds --on-track [--draftees draftees.pkl]

A row per prospect per export (2038-41, the own-scout files, unsigned
amateurs left out): his ceiling (the potential profile's model lines) and
readiness (FULL_TIME's), both on the full-time scale as the draft fit has
them, and outcome A on the latest snapshot.

The fit models the remaining gap (open question 1):

    E[A] = keep x his WAR now + close x (ceiling - his WAR now)

with his WAR now floored at 0, and keep and close both odds, fit together.
Prospects often end below their WAR now (about 45% by a quarter WAR or
more), so keep is fit, not 1: on his age, his WAR now and the years to the
outcome. close is the draft fit's shape (ceiling, readiness by age, role,
makeup tapered) on age knots 21 / 23 / 25. Level drops out once age and
readiness are in, and so does age for level (open question 3). Held out, a
multiplier in the draft fit's shape ranks about as well but overshoots the
top of the board (its top 25 realized 0.76 of predicted, half of them
predicted past their own ceiling); this is calibrated there.

Held out by player (every export of a player in one fold) and judged per
export, against today's prospect board. --on-track instead pools the table
with the draft fit's (a draftee is a prospect on draft day) and describes the
gap by age (step 1).
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scipy import optimize
from scipy.stats import spearmanr

from context import default_base_dir
from ranking import development
from ranking import draft_odds as board_odds
from ranking.fitting import draft_odds
from ranking.stages.companion import BAT_LINES
from ranking.hitter_talent import ARTIFACTS_DIR
from ranking.fitting.ceiling_panel import _prospects

PROSPECT_YEARS = range(2038, 2042)
# his level as an order, as the snapshot has them (the API's levels have no
# A+: it's A there too). Level "-" is an unsigned amateur, off the board
LEVELS = {"INT": 0, "R": 1, "A-": 2, "A": 3, "A+": 3, "AA": 4, "AAA": 5, "MLB": 6}
ARTIFACT = "prospect_odds_v1"
# judgment (2026-11-12, you): the share of the gap he closes at each age, x
# 21's - one smooth curve in place of the fitted age terms, the on-schedule
# relief and the end of development (the data's own: 23 about x0.64, 25
# x0.13, with a cliff wherever two of those met). Between the ages it's
# linear, held at the ends; the rest of the fit is fit around it
AGE_CURVE = ((21, 1.0), (22, 0.9), (23, 0.8), (24, 0.73), (25, 0.6), (26, 0.38), (27, 0.15), (28, 0.05))
# the holding odds' age, held within these
KEEP_AGES = (21, 25)
AGE_REFERENCE = 23
# judgment (2026-11-11, you): below BRIDGE's first age a prospect is valued
# on the draft fit's expectation, as a draftee of his age, blended linearly
# into this fit by its second - no export settles a teen, and a teen in the
# minors is closer to a draftee than to a 21-year-old pro. It reads him as
# developed as this fit does, a hitter on his bat (2026-11-12, you): a glove
# and legs at their ceiling already put two teen infielders past it
BRIDGE = (20, 22)
# judgment (2026-11-12, you): the closing odds' base, at 21, set so the fit's
# expectation for the prospects within these ages matches what they realized
# - AGE_CURVE is judgment past them, and the older prospects' shortfall from
# it otherwise pulls every age's base down
ANCHOR_AGES = (20, 22)
# personality in the closing odds: the draft fit's makeup, and adaptability
MAKEUP = {**draft_odds.MAKEUP, "AD H": lambda d: d.ad == "H", "AD L": lambda d: d.ad == "L"}
# years from the export to the outcome's snapshot the odds are read at
REFERENCE_YEARS = 3.0
# the WAR now the holding odds read, at most
KEEP_NOW_CLIP = 3.0
RIDGE = 1e-3
# judgment on the closing odds: {column: its coefficient}, held near it by a
# tight prior, the rest fit around it
# (2026-11-11, you):
# - "log potential" 0: the share of the gap he closes doesn't fall as his
#   ceiling rises (the data's -0.80 rests on a few dozen 5+ ceilings, judged
#   at 25, before a high ceiling usually pays off)
# - "SP" -0.40 (the data's -0.93): with UPSIDE, 6 starters in the 2042
#   board's top 25 (at least 5, you'd take 10-12) and 36 pitchers in its top
#   100 (about 30-35); a softer penalty adds pitchers to the top 100 faster
#   than to the top 25
CLOSE_JUDGMENT = {"log potential": 0.0, "SP": -0.40}
# judgment on the holding odds, as CLOSE_JUDGMENT (2026-11-12, you): "age"
# at the fit's own before AGE_CURVE (-0.31 a year); fit around the curve
# it takes the older prospects' shortfall instead (-1.07)
KEEP_JUDGMENT = {"age": -0.31}
JUDGMENT_SD = 0.01
# judgment (2026-11-11, you): the board weighs what he's expected to add by
# developing this many times what he keeps of his WAR now - upside over
# present production. Held out on A it costs about a seventh of the top 25's
# realized WAR (plans/prospect-odds-plan.md, "Upside")
UPSIDE = 2.0
FOLDS = 5
BOOTSTRAPS = 50
# a player who reached his ceiling: realized this share of it or more
REACHED = 0.75
CEILING_BINS = [0.5, 2.0, 3.5, 99]


def prospect_table(base: Path, league: str) -> pd.DataFrame:
    """One row per prospect per export with an outcome to judge."""
    from eval_rankings import ARRIVAL_AGE, read_snapshot
    from league_snapshot import coerce_gf
    from models.game_players import GamePlayer

    snap_dir = base / "league_snapshots" / league
    season = int(json.loads((snap_dir / "meta.json").read_text())["league_date"][:4])
    snapshot = read_snapshot(snap_dir / "players.csv")
    now = draft_odds._raw_war(draft_odds._rank("full_time", [GamePlayer(r) for r in snapshot.values()]))
    stats_dir = base / "league_stats" / league
    war_seasons = {pid: dict(zip(g.year, g.war)) for pid, g in draft_odds._mlb_war_by_year(stats_dir).groupby("player_id")}
    pa_seasons = {pid: dict(zip(g.year, g.pa)) for pid, g in draft_odds._mlb_pa_by_year(stats_dir).groupby("player_id")}
    rows = []
    for year in PROSPECT_YEARS:
        export = _prospects(base, league, year)
        # older exports carry only current velocity (as the ceiling panel reads them)
        players = [GamePlayer({**r, "G/F": coerce_gf(r.get("G/F")), "VT": r.get("VT") or r.get("VELO")})
                   for r in export]
        board = {x.id: x for x in _before_odds().rank(players, batch_size=max(len(players), 1))}
        potential = draft_odds._raw_war(board.values())
        now_ranked = draft_odds._rank("full_time", players)
        current, bat = _side_war(now_ranked), draft_odds._bat_war(now_ranked)
        pot_split, now_split = draft_odds._split_war(board.values()), draft_odds._split_war(now_ranked)
        pulled = _pulled(export, year)
        for r, player in zip(export, players):
            pid = r["ID"]
            if pid not in potential or pid not in current or r.get("Lev") not in LEVELS:
                continue
            age, snap = int(r["Age"]), snapshot.get(pid)
            age_now = int(snap["Age"]) if snap else age + season - year
            rows.append({
                "source": "prospects", "class": year, "id": int(pid), "name": r["Name"], "pos": r["POS"],
                "age": age, "age_exact": (pulled - player.birth_date).days / 365.2425 if player.birth_date else age + 0.5,
                "level": r["Lev"], "level_n": LEVELS[r["Lev"]], "org": r.get("ORG"),
                "ovr": pd.to_numeric(r.get("OVR"), errors="coerce"), "pot": pd.to_numeric(r.get("POT"), errors="coerce"),
                "we": r.get("WE"), "int": r.get("INT"), "ad": r.get("AD"), "prone": r.get("Prone"),
                "velo": r.get("VT") or r.get("VELO"), "stuff": r.get("STU P"), "pitches": r.get("PIT"),
                "war_pot": potential[pid][0], "side": potential[pid][1], "role": potential[pid][2],
                # his WAR now on his ceiling's side, as the board reads it
                "readiness": current[pid].get(potential[pid][1], 0.0),
                # how developed a hitter is: his bat's WAR now alone (batting
                # and platoon) - his glove and legs have no potential ratings,
                # so they're at their ceiling already
                "bat": bat[pid],
                "board": board[pid].pre_demand_score, "board_rank": board[pid].pre_demand_rank,
                "factors": draft_odds._factors(board[pid]),
                "gone": snap is None, "age_now": age_now, "years": season + 0.85 - year - pulled.timetuple().tm_yday / 365,
                "a": 0.0 if snap is None else now[pid][0], "a_settled": age_now >= ARRIVAL_AGE,
                # his ceiling and WAR now by part (bat, glove, run:
                # plans/draft-glove-plan.md), and his MLB WAR and PA each season
                # from the export's on
                **{f"pot_{k}": v for k, v in pot_split[pid].items()},
                **{f"now_{k}": v for k, v in now_split[pid].items()},
                "mlb_war": {y: w for y, w in war_seasons.get(int(pid), {}).items() if y >= year},
                "mlb_pa": {y: n for y, n in pa_seasons.get(int(pid), {}).items() if y >= year},
            })
        print(f"  {league}-{year}-prospects: {len(export)}", file=sys.stderr)
    d = pd.DataFrame(rows)
    d["group"] = np.where(d.side == "batting", "hitter", d.role)
    return d


def _before_odds():
    """The prospect board before these odds, the baseline they're judged
    against: potential ratings on the development factors and the legacy
    modifiers (ranking/development.py)."""
    from dataclasses import replace

    from ranking.profiles import POTENTIAL
    from ranking.ranker import Ranker

    return Ranker(replace(POTENTIAL, odds=None, companions=()))


def _side_war(ranked) -> dict:
    """{id: {side: WAR from that side's model lines}}, as the readiness
    companion keeps them (ranking/stages/companion.py)."""
    from ranking.ledger import BATTING, MODEL, PITCHING

    return {r.id: {side: sum(line.delta for line in r.ledger.lines if line.stage == MODEL and line.side == side) / 10
                   for side in (BATTING, PITCHING)} for r in ranked}


def _pulled(export, year) -> date:
    """The day an export was pulled, near enough: the latest birthday in its
    year that its Ages show had passed (the exports are pulled anywhere from
    February to July)."""
    passed = date(year, 1, 1)
    for r in export:
        try:
            dob = datetime.strptime(r["DOB"], "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        if year - dob.year == int(r["Age"]):
            passed = max(passed, date(year, dob.month, min(dob.day, 28 if dob.month == 2 else dob.day)))
    return passed


def pooled(prospects: pd.DataFrame, draftees: pd.DataFrame) -> pd.DataFrame:
    """Both tables' settled rows with a ceiling worth judging, on the columns
    they share, with the gap and the realized share of it."""
    cols = ["source", "class", "id", "name", "pos", "age", "group", "war_pot", "readiness", "a", "a_settled"]
    d = pd.concat([draftees.assign(source="draft")[cols], prospects[cols]], ignore_index=True)
    d = d[d.a_settled & (d.war_pot >= draft_odds.MIN_POTENTIAL_WAR)].copy()
    d["gap"] = (d.war_pot - d.readiness).clip(lower=0)
    d["realized"] = d.a.clip(lower=0) / d.war_pot
    d["share"] = ((d.a - d.readiness) / d.gap.where(d.gap > 0)).clip(0, 1)
    d["ceiling_bin"] = pd.cut(d.war_pot, CEILING_BINS, labels=["0.5-2", "2-3.5", "3.5+"])
    return d


def expected_gap(d: pd.DataFrame) -> pd.DataFrame:
    """The median gap, by age and ceiling, of the players who went on to reach
    their ceiling - the gap of a player on track at that age."""
    reached = d[d.realized >= REACHED]
    return reached.pivot_table(index="age", columns="ceiling_bin", values="gap", aggfunc="median", observed=True)


def describe(d: pd.DataFrame):
    ages = d.age.clip(17, 26)
    print("\nrows by age and source (settled, ceiling 0.5+):")
    print(d.assign(age=ages).pivot_table(index="age", columns="source", values="id", aggfunc="size", fill_value=0))
    print(f"\nthe gap (ceiling - WAR now) by age, everyone, and of the players who reached {REACHED:.0%}+ of it:")
    everyone = d.assign(age=ages).pivot_table(index="age", columns="ceiling_bin", values="gap", aggfunc="median",
                                              observed=True)
    on_track = expected_gap(d.assign(age=ages))
    print(pd.concat({"everyone": everyone, "reached": on_track}, axis=1).round(2))
    print("\nshare reached by age and ceiling:")
    print(d.assign(age=ages, hit=d.realized >= REACHED).pivot_table(
        index="age", columns="ceiling_bin", values="hit", aggfunc="mean", observed=True).round(2))

    d = d.assign(age=ages, ahead=ahead(d.assign(age=ages)))
    d["ahead_bin"] = pd.cut(d.ahead, AHEAD_BINS)
    d["age_group"] = pd.cut(d.age, [0, 20, 21, 22, 23, 24, 99], labels=["<=20", "21", "22", "23", "24", "25+"])
    regular = d.group.map(REGULAR)
    d = d.assign(reached=d.realized >= REACHED, regular=d.a >= regular)
    for label, part in (("ceiling 0.5+", d), ("ceiling 2+", d[d.war_pot >= 2])):
        print(f"\n{label}: by how far ahead of his age's typical gap (WAR), realized share of the ceiling, "
              f"reached {REACHED:.0%}+, a regular:")
        t = part.groupby(["age_group", "ahead_bin"], observed=True).agg(
            n=("id", "size"), realized=("realized", "mean"), reached=("reached", "mean"), regular=("regular", "mean"))
        print(t[t.n >= 15].round(2).to_string())


# a regular, on the full-time scale (draft_odds_v1's "regular")
REGULAR = {"hitter": 1.707, "SP": 1.981, "RP": 0.187}
AHEAD_BINS = [-99, -1.5, -0.5, 0.5, 1.5, 99]


def ahead(d: pd.DataFrame) -> pd.Series:
    """How far ahead of the typical gap for his age and ceiling he is, in WAR:
    each age's gap fit as a line in the ceiling, minus his own."""
    out = pd.Series(np.nan, index=d.index)
    for _, g in d.groupby("age"):
        slope, intercept = np.polyfit(g.war_pot, g.gap, 1)
        out[g.index] = intercept + slope * g.war_pot - g.gap
    return out


# -- the fit (step 3) -----------------------------------------------------------

def _sigmoid(z):
    return 1 / (1 + np.exp(-z))


def now_war(d: pd.DataFrame) -> pd.Series:
    """His WAR now, floored at replacement: what he can hold onto."""
    return d.readiness.clip(lower=0)


def gap(d: pd.DataFrame) -> pd.Series:
    return (d.war_pot - now_war(d)).clip(lower=0)


def developed(d: pd.DataFrame) -> pd.Series:
    """How developed he is, as the closing odds read it: a hitter's bat WAR
    now alone (his glove and legs are at their ceiling already), a pitcher's
    WAR now."""
    return pd.Series(np.where(d.side == "batting", d.bat, d.readiness), index=d.index)


def age_curve(age) -> np.ndarray:
    """The share of the gap he closes at `age`, x 21's (AGE_CURVE)."""
    ages, values = zip(*AGE_CURVE)
    return np.interp(np.asarray(age, dtype=float), ages, values)


def design(d: pd.DataFrame) -> pd.DataFrame:
    """The closing odds' columns, at 21 (AGE_CURVE takes it to his age); the
    reference prospect is a hitter, REFERENCE_WAR at potential, 0 WAR
    developed, normal makeup, REFERENCE_YEARS from the outcome."""
    taper = np.vectorize(development.weight)(d.war_pot)
    potential = np.log(d.war_pot.clip(lower=draft_odds.LOG_FLOOR) / draft_odds.REFERENCE_WAR)
    cols = {"log potential": potential, "developed": developed(d).clip(*draft_odds.READINESS_CLIP)}
    for g in ("SP", "RP"):
        cols[g] = (d.group == g).astype(float)
    for label, test in MAKEUP.items():
        cols[label] = test(d).astype(float) * taper
    cols["years"] = d.years - REFERENCE_YEARS
    return pd.DataFrame(cols, index=d.index)


def keep_design(d: pd.DataFrame) -> pd.DataFrame:
    """The holding odds' columns: his age (held within KEEP_AGES), the years
    to the outcome and his WAR now (to KEEP_NOW_CLIP)."""
    return pd.DataFrame({"age": d.age_exact.clip(*KEEP_AGES) - AGE_REFERENCE,
                         "years": d.years - REFERENCE_YEARS,
                         "now": now_war(d).clip(upper=KEEP_NOW_CLIP)}, index=d.index)


class GapFit:
    """E[A] = keep x his WAR now + close x the gap, both odds (logistic), fit
    together on the Poisson deviance of A; the closing odds' `judgment`
    columns held near their values by a tight prior (JUDGMENT_SD), the rest
    fit around them."""

    def __init__(self, judgment=None, keep_judgment=None):
        self.judgment = CLOSE_JUDGMENT if judgment is None else judgment
        self.keep_judgment = KEEP_JUDGMENT if keep_judgment is None else keep_judgment

    def fit(self, d: pd.DataFrame) -> "GapFit":
        x, k = design(d).values, keep_design(d).values
        y, now = d.a.clip(lower=0).values, now_war(d).values
        short = gap(d).values * age_curve(d.age_exact.values)
        nx = x.shape[1] + 1
        names = list(design(d.head(1)).columns)
        held = np.array([n in self.judgment for n in names])
        mean = np.array([self.judgment.get(n, 0.0) for n in names])
        # the ridge on the free columns, the judgment's prior on the held
        weight = np.where(held, 0.5 / JUDGMENT_SD ** 2, RIDGE)
        keep_names = list(keep_design(d.head(1)).columns)
        keep_mean = np.array([self.keep_judgment.get(n, 0.0) for n in keep_names])
        keep_weight = np.where([n in self.keep_judgment for n in keep_names], 0.5 / JUDGMENT_SD ** 2, RIDGE)

        def loss(w):
            b, c = w[:nx], w[nx:]
            pk, pc = _sigmoid(c[0] + k @ c[1:]), _sigmoid(b[0] + x @ b[1:])
            mu = np.clip(pk * now + pc * short, 1e-6, None)
            r = 1 - y / mu
            gk, gc = r * now * pk * (1 - pk), r * short * pc * (1 - pc)
            value = (np.sum(mu - y * np.log(mu)) + np.sum(weight * (b[1:] - mean) ** 2)
                     + np.sum(keep_weight * (c[1:] - keep_mean) ** 2))
            grad = np.concatenate([[gc.sum()], x.T @ gc + 2 * weight * (b[1:] - mean), [gk.sum()],
                                   k.T @ gk + 2 * keep_weight * (c[1:] - keep_mean)])
            return value, grad
        w0 = np.concatenate([[-1.0], mean, [0.0], keep_mean])
        w = optimize.minimize(loss, w0, jac=True, method="L-BFGS-B").x
        self.close, self.keep = w[:nx], w[nx:]
        self._anchor(d)
        return self

    def _anchor(self, d: pd.DataFrame):
        """Shift the closing odds' intercept so the expectation for the
        prospects within ANCHOR_AGES sums to what they realized."""
        young = d[(d.age_exact >= ANCHOR_AGES[0]) & (d.age_exact < ANCHOR_AGES[1])]
        realized = young.a.clip(lower=0).sum()

        def short(shift):
            self.close[0] += shift
            out = self.predict(young, at_reference=False).sum() - realized
            self.close[0] -= shift
            return out
        self.close[0] += optimize.brentq(short, -3, 3)

    def parts(self, d: pd.DataFrame, at_reference=True) -> tuple:
        """(keep, close) per row, read REFERENCE_YEARS from the outcome; close
        at his age (the odds at 21 x AGE_CURVE)."""
        e = d.assign(years=REFERENCE_YEARS) if at_reference else d
        return (_sigmoid(self.keep[0] + keep_design(e).values @ self.keep[1:]),
                _sigmoid(self.close[0] + design(e).values @ self.close[1:]) * age_curve(d.age_exact.values))

    def predict(self, d: pd.DataFrame, at_reference=True) -> np.ndarray:
        """E[A] (the bridge has nothing to judge here: no teen is settled)."""
        keep, close = self.parts(d, at_reference)
        return keep * now_war(d).values + close * gap(d).values

    def value(self, d: pd.DataFrame) -> np.ndarray:
        """What the board ranks on: what he keeps of his WAR now, plus UPSIDE
        x what he's expected to add by developing, with the judgment."""
        keep, _ = self.parts(d)
        held = keep * now_war(d).values
        return held + UPSIDE * (self.predict(d) - held)


def able(prospects: pd.DataFrame) -> pd.DataFrame:
    """The settled prospects with a ceiling worth judging."""
    d = prospects[prospects.a_settled & (prospects.war_pot >= draft_odds.MIN_POTENTIAL_WAR)]
    return d.reset_index(drop=True)


def held_out(d: pd.DataFrame, scale=None) -> tuple:
    """(by key, {key: predictions}): FOLDS fits, a player's every export in
    one fold, so none is judged by a fit that saw him; each export ranked on
    its own, the mean over exports of rho and the top k's mean A - for the
    board, the fit's expectation and what the board ranks on (`value`), both
    with the judgment and times `scale`. The predictions are the
    expectation's ("fit") and the value's ("value"), without `scale`."""
    folds = d.id.values % FOLDS
    pred, value = np.zeros(len(d)), np.zeros(len(d))
    for f in range(FOLDS):
        train, test = folds != f, folds == f
        model = GapFit().fit(d[train])
        pred[test] = model.predict(d[test])
        value[test] = model.value(d[test])
    scale = 1.0 if scale is None else scale
    scores = {"board": d.board.values, "expected": pred * scale, f"value (upside x{UPSIDE:g})": value * scale}
    rows = []
    for key, s in scores.items():
        for year, g in d.groupby("class"):
            y, x = g.a.clip(lower=0).values, s[g.index]
            order = np.argsort(-x)
            rows.append({"key": key, "class": year, "rho": spearmanr(x, y)[0],
                         **{f"top {k}": y[order[:k]].mean() for k in draft_odds.TOP_K}})
    table = pd.DataFrame(rows).groupby("key", sort=False).mean().drop(columns="class")
    return table, {"board": d.board.values, "fit": pred, "value": value}


def _names(d) -> tuple:
    return ["intercept", *design(d.head(1)).columns], ["intercept", *keep_design(d.head(1)).columns]


def report_fit(d: pd.DataFrame, model: GapFit):
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(BOOTSTRAPS):
        m = GapFit().fit(d.iloc[rng.integers(0, len(d), len(d))])
        boots.append(np.concatenate([m.close, m.keep]))
    lo, hi = np.percentile(boots, [5, 95], axis=0)
    close_names, keep_names = _names(d)
    print(f"\nthe fit: n={len(d)} ({d.id.nunique()} players), mean A {d.a.clip(lower=0).mean():.2f}, "
          f"mean potential WAR {d.war_pot.mean():.2f}, mean WAR now {now_war(d).mean():.2f}")
    names = [f"close: {n}" for n in close_names] + [f"keep: {n}" for n in keep_names]
    for name, c, l, h in zip(names, np.concatenate([model.close, model.keep]), lo, hi):
        print(f"  {name:>29} {c:+.2f}   90% {l:+.2f} to {h:+.2f}")
    keep, close = model.parts(d)
    print(f"  at the reference: keeps {_sigmoid(model.keep[0]):.0%} of his WAR now, closes "
          f"{_sigmoid(model.close[0]):.0%} of the gap; on average {keep.mean():.0%} and {close.mean():.0%}")


def report_calibration(d: pd.DataFrame, pred: np.ndarray):
    """Realized / predicted A, held out, by level, age and role: what the fit
    leaves out (level, age for level) should come out flat."""
    q = d.assign(pred=pred, y=d.a.clip(lower=0), age_g=d.age.clip(20, 25),
                 age_for_level=(d.age - d.level_n.map(d.groupby("level_n").age.median())).clip(-2, 2))
    q["rank"] = pd.cut(q.groupby("class").pred.rank(ascending=False), [0, 25, 50, 100, 200, np.inf],
                       labels=["1-25", "26-50", "51-100", "101-200", "201+"])
    print("\nrealized / predicted, held out:")
    for by in ("rank", "level", "age_g", "age_for_level", "group"):
        g = q.groupby(by, observed=True)
        print(f"  {by:>14}  " + "  ".join(f"{k} {v:.2f} ({n})" for (k, v), n in
                                       zip((g.y.sum() / g.pred.sum()).items(), g.size())))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--table", help="cache the prospect table here (a .pkl); read it when it exists")
    p.add_argument("--on-track", action="store_true", help="step 1's pooled description instead of the fit")
    p.add_argument("--draftees", help="the draft fit's cached table (draft_odds --table), for --on-track")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    if args.table and Path(args.table).exists():
        prospects = pd.read_pickle(args.table)
    else:
        prospects = prospect_table(base, args.league)
        if args.table:
            prospects.to_pickle(args.table)
    if args.on_track:
        if args.draftees and Path(args.draftees).exists():
            draftees = pd.read_pickle(args.draftees)
        else:
            draftees = draft_odds.draftee_table(base, args.league)
        describe(pooled(prospects, draftees))
        return

    d = able(prospects)
    model = GapFit().fit(d)
    report_fit(d, model)
    _, scores = held_out(d)
    pred = scores["fit"]
    report_calibration(d, pred)

    # no pitcher balance: the starter judgment (CLOSE_JUDGMENT) sets the mix
    kept = draft_odds.kept(d)
    print("\npitcher share by rank within export, held out, with the kept lines:")
    shares = {"board": draft_odds.pitcher_shares(d, "board"),
              "expected": draft_odds.pitcher_shares(d.assign(x=pred * kept), "x"),
              "value": draft_odds.pitcher_shares(d.assign(x=scores["value"] * kept), "x")}
    for label, x in shares.items():
        print(draft_odds._shares_line(label, x))
    table, _ = held_out(d, kept)
    print(f"\nheld out ({FOLDS} folds by player), mean per export, judged on A, with the kept lines:")
    print("\n".join("  " + line for line in table.round(3).to_string().splitlines()))

    close_names, keep_names = _names(d)
    draft = board_odds.load()
    artifact = {
        "version": ARTIFACT,
        "outcome": "A: v2 full-time WAR on current ratings in the latest snapshot, 25+, 0 once gone",
        "min_potential_war": draft_odds.MIN_POTENTIAL_WAR,
        "log_floor": draft_odds.LOG_FLOOR,
        "reference_war": draft_odds.REFERENCE_WAR,
        # E = keep x his WAR now (floored at 0) + close x (ceiling - WAR now),
        # each odds = 1 / (1 + exp(-(intercept + sum coef x column))), close
        # at 21 times age_curve at his age; columns as
        # ranking/fitting/prospect_odds.py's design / keep_design, read
        # REFERENCE_YEARS from the outcome (years = 0). "developed" is a
        # hitter's bat WAR now (bat_lines), a pitcher's WAR now
        "close": {"intercept": round(float(model.close[0]), 4),
                  "coef": {n: round(float(c), 4) for n, c in zip(close_names[1:], model.close[1:])},
                  "developed_clip": list(draft_odds.READINESS_CLIP), "judgment": CLOSE_JUDGMENT,
                  "bat_lines": list(BAT_LINES)},
        "keep": {"intercept": round(float(model.keep[0]), 4),
                 "coef": {n: round(float(c), 4) for n, c in zip(keep_names[1:], model.keep[1:])},
                 "now_clip": KEEP_NOW_CLIP},
        # judgment: [age, share of the gap closed x 21's], linear between, held
        # at the ends; the holding odds' age held within keep_ages
        "age_curve": [list(x) for x in AGE_CURVE], "keep_ages": list(KEEP_AGES), "age_reference": AGE_REFERENCE,
        # judgment: the draft odds' expectation (as a draftee of his age, his
        # readiness "developed") below `ages`' first, blended linearly into
        # these by its second; the closing odds' intercept matches what the
        # prospects within anchor_ages realized
        "bridge": {"draft_odds": draft.version, "ages": list(BRIDGE)}, "anchor_ages": list(ANCHOR_AGES),
        "taper": [development.FULL_WEIGHT_WAR, development.TAPERED_WAR, development.TAPERED_WEIGHT],
        "pitcher_balance": 1.0,
        # what the board ranks on: kept x WAR now + upside x (E - kept x WAR now)
        "upside": UPSIDE,
        "judgment": {"kept": list(draft_odds.KEPT), "velocity_steps": [list(x) for x in board_odds.VELOCITY_STEPS],
                     "replaces": list(board_odds.REPLACES)},
        "regular": draft.regular,
        "check": {"held_out": table.round(3).to_dict(orient="index"),
                  "pitcher_share": {k: [round(x, 3) for x in v] for k, v in shares.items()}},
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "league": args.league,
            "exports": [PROSPECT_YEARS.start, PROSPECT_YEARS.stop - 1],
            "prospects": {"rows": len(d), "players": int(d.id.nunique())},
        },
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
