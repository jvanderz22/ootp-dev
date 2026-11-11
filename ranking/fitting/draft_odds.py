"""Fit the draft odds - the chance he gets there (plans/draft-odds-plan.md) -
and write their artifact.

    python -m ranking.fitting.draft_odds --data-dir fly_data [--table draftees.pkl]

The v2 board values a draftee at the WAR his potential ratings are worth in a
full-time role: his value if he gets there. This fits how much of that a
draftee like him actually realizes, from the league's past classes.

Every draftee is scored by v2 as of draft day, model lines only (before any
modifier): on his potential ratings (the ceiling, the draft profile) and on
his current ones (readiness - draft-day OVR is 20 for nearly all of them, so
it can't be used). Everything is on the full-time scale (ranking/profiles.py's
FULL_TIME for current ratings): WAR at a full-time role over StatsPlus's
replacement, with none of the league's roster pricing, as the ceiling is.
Two outcomes, as decided 2026-11-09:

- A, the fit: v2's full-time WAR on his current ratings in the latest
  snapshot, for everyone ARRIVAL_AGE or older by then, 0 once he's left the
  league.
- B, the check: his MLB WAR through age B_LAST_AGE, for players whose window
  is complete.

A Poisson regression (log link) of max(outcome, 0) on log potential WAR,
readiness, his role at potential (hitter, SP, RP), age at draft and makeup.
The age factors change with potential (AGE_BY_POTENTIAL): a teen's runway is
worth less the higher his ceiling already is, and a college senior's penalty
shrinks. Without that the fit drops 22-year-olds who went on to be stars and
ranks the top 25 no better than the board (step 2, 2026-11-09); velocity,
Stuff, pitch count, a potential curve per side and weighting the top didn't
help.
The makeup columns are tapered by potential WAR as ranking/development.py
tapers them (decided 2026-11-09), so a fitted factor is its full-weight value.
Fit on draftees with MIN_POTENTIAL_WAR or more: below that the board barely
ranks them and neither outcome has anything to say.

Then, leaving one class out at a time, the fit's ranking against today's board
(pre-demand) on both outcomes; and the pitcher share by rank bucket, with the
one side-balance factor on pitchers that brings the buckets to 50/50 on
average (the plan's "Risk" section). Both judge the board as it would ship:
the fit times the lines it doesn't replace (KEPT), then the balance.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression, PoissonRegressor

from context import default_base_dir
from ranking import development
from ranking.fitting import ceiling_panel
from ranking.hitter_talent import ARTIFACTS_DIR

ARTIFACT = "draft_odds_v1"
FIT_CLASSES = range(2033, 2038)     # old enough that outcome A has settled
B_LAST_AGE = 26
MIN_POTENTIAL_WAR = 0.5
LOG_FLOOR = 0.1                     # potential WAR floor inside the log
REFERENCE_WAR = 3.0                 # potential WAR the age factors are read at
READINESS_CLIP = (-4.0, 3.0)
ALPHA = 1e-4
BOOTSTRAPS = 200
AGE_GROUPS = {"18": (0, 18), "19": (19, 19), "20": (20, 20), "22": (22, 99)}   # 21 is the reference
AGE_BY_POTENTIAL = {"19": (0, 19), "22": (22, 99)}
MAKEUP = {
    "WE H": lambda d: d.we == "H", "WE L": lambda d: d.we == "L",
    "INT H": lambda d: d["int"] == "H", "INT L": lambda d: d["int"] == "L",
    "fragile": lambda d: d.prone.isin(["Fragile", "Wrecked"]),
    "durable": lambda d: d.prone.isin(["Durable", "Iron Man"]),
}
# the board's lines the odds don't replace (plans/draft-odds-plan.md, C2): they
# stay on top of the odds as judgment, so the balance and the held-out checks
# judge the board with them on
KEPT = ("ScoutingAccuracyModifier", "DraftSecondaryPersonalityModifier", "DraftPitcherStuffModifier",
        "PitcherVelocityModifier", "BatterHitProfileModifier", "switch hitter")
BUCKETS = [(1, 25), (26, 50), (51, 100), (101, 200), (201, 400)]
# the growth odds (B6): outgrowing the ceiling (ranking/fitting/ceiling_panel.py)
# fit on the panel's later classes, whose exports are closest to carrying
# potential velocity, and checked on outcome A's
GROWTH_PANEL_CLASSES = range(2035, 2042)
GROWTH_C = 1.0                      # logistic regularisation: events are rare
REFERENCE_YEARS = 7                 # years after the draft the odds are read at
# judgment (2026-11-10): the data's sample is small, and you'd keep a work
# ethic and a velocity bump on outgrowing even where it doesn't fully show
# them (panel: WE H x1.06, x1.02 per mph; the POT look: x1.33, x1.11). Odds,
# held near these by a tight prior; the other columns are fit.
GROWTH_JUDGMENT = {"WE H": 1.30, "velocity": 1.06}
JUDGMENT_SD = 0.05
TOP_K = (25, 50, 100)


def _raw_war(ranked) -> dict:
    """{id: (WAR from the model lines alone, side, role)}, on StatsPlus's
    scale (the potential, draft and full-time profiles price no roster)."""
    from ranking.ledger import MODEL

    out = {}
    for r in ranked:
        points = sum(line.delta for line in r.ledger.lines if line.stage == MODEL and r.ledger.counted(line))
        out[r.id] = ((points - 50) / 10, r.ledger.side, r.ledger.role)
    return out


def _factors(result) -> dict:
    """{label: factor} of the board's modifier and development lines on his side."""
    from ranking.ledger import DEVELOPMENT, MODIFIERS

    return {line.label: float(line.stat[1:]) for line in result.ledger.lines
            if line.stage in (MODIFIERS, DEVELOPMENT) and result.ledger.counted(line) and line.stat}


def _rank(method, players):
    from ranking import get_ranker

    return get_ranker(method).rank(players, batch_size=max(len(players), 1))


def _mlb_war_by_year(stats_dir) -> pd.DataFrame:
    frames = []
    for kind in ("bat", "pitch"):
        for path in sorted((Path(stats_dir) / kind).glob("*.csv")):
            x = pd.read_csv(path, usecols=["player_id", "year", "split_id", "level_id", "war"])
            frames.append(x[(x.split_id == 1) & (x.level_id == 1)])
    return pd.concat(frames).groupby(["player_id", "year"]).war.sum().reset_index()


def draftee_table(base: Path, league: str) -> pd.DataFrame:
    """One row per scored draftee of every class with an outcome to judge."""
    from eval_rankings import ARRIVAL_AGE, _class_players, read_classes, read_snapshot
    from models.game_players import GamePlayer

    snap_dir = base / "league_snapshots" / league
    season = int(json.loads((snap_dir / "meta.json").read_text())["league_date"][:4])
    snapshot = read_snapshot(snap_dir / "players.csv")
    now = _raw_war(_rank("full_time", [GamePlayer(r) for r in snapshot.values()]))
    war = _mlb_war_by_year(base / "league_stats" / league)
    last_stats = int(war.year.max())
    seasons = {pid: dict(zip(g.year, g.war)) for pid, g in war.groupby("player_id")}
    names = {f"{league}-{y}-draft" for y in range(FIT_CLASSES.start, season)}
    rows = []
    for name, class_rows in read_classes([Path("datasets"), base / "datasets"], league, names).items():
        year = int(name.split("-")[1])
        players = _class_players(class_rows)
        board = {r.id: r for r in _rank("draft_class", players)}
        potential, current = _raw_war(board.values()), _raw_war(_rank("full_time", players))
        for r in class_rows:
            pid = r["ID"]
            if pid not in board:
                continue
            age, snap = int(r["Age"]), snapshot.get(pid)
            age_now = int(snap["Age"]) if snap else age + season - year
            last_b = year + B_LAST_AGE - age
            rows.append({
                "class": year, "id": int(pid), "name": r["Name"], "pos": r["POS"], "age": age,
                "we": r["WE"], "int": r["INT"], "prone": r["Prone"],
                "velo": r.get("VT") or r.get("VELO"), "stuff": r.get("STU P"), "pitches": r.get("PIT"),
                "stamina": r.get("STM"),
                "war_pot": potential[pid][0], "side": potential[pid][1], "role": potential[pid][2],
                "readiness": current[pid][0],
                "board": board[pid].pre_demand_score, "board_rank": board[pid].pre_demand_rank,
                "factors": _factors(board[pid]),
                "gone": snap is None, "age_now": age_now,
                "a": 0.0 if snap is None else now[pid][0], "a_settled": age_now >= ARRIVAL_AGE,
                "b": sum(w for y, w in seasons.get(int(pid), {}).items() if y <= last_b), "b_settled": last_b <= last_stats,
            })
        print(f"  {name}: {len(players)} draftees", file=sys.stderr)
    d = pd.DataFrame(rows)
    d["group"] = np.where(d.side == "batting", "hitter", d.role)
    return d


def design(d: pd.DataFrame) -> pd.DataFrame:
    """The regression's columns; the reference draftee is a hitter, 21 at the
    draft, REFERENCE_WAR at potential, 0 WAR on his current ratings, normal
    makeup."""
    taper = np.vectorize(development.weight)(d.war_pot)
    potential = np.log(d.war_pot.clip(lower=LOG_FLOOR) / REFERENCE_WAR)
    cols = {"log potential": potential, "readiness": d.readiness.clip(*READINESS_CLIP)}
    for g in ("SP", "RP"):
        cols[g] = (d.group == g).astype(float)
    for label, (lo, hi) in AGE_GROUPS.items():
        cols[f"age {label}"] = d.age.between(lo, hi).astype(float)
    for label, (lo, hi) in AGE_BY_POTENTIAL.items():
        cols[f"age {label} x potential"] = potential * d.age.between(lo, hi)
    for label, test in MAKEUP.items():
        cols[label] = test(d).astype(float) * taper
    return pd.DataFrame(cols, index=d.index)


def fit(d: pd.DataFrame, outcome: str) -> PoissonRegressor:
    return PoissonRegressor(alpha=ALPHA, max_iter=5000).fit(design(d).values, d[outcome].clip(lower=0).values)


def bootstrap(d: pd.DataFrame, outcome: str, seed=0) -> np.ndarray:
    """(2, n coefficients): the 5th and 95th percentiles over resampled draftees."""
    rng, x, y = np.random.default_rng(seed), design(d).values, d[outcome].clip(lower=0).values
    coefs = []
    for _ in range(BOOTSTRAPS):
        i = rng.integers(0, len(d), len(d))
        coefs.append(PoissonRegressor(alpha=ALPHA, max_iter=5000).fit(x[i], y[i]).coef_)
    return np.percentile(coefs, [5, 95], axis=0)


def _readable(name, c) -> str:
    if name == "log potential" or name.endswith("x potential"):
        return f"{c:+.2f}"
    return f"x{np.exp(c):.2f}"


def report_fit(label, d, outcome, model):
    lo, hi = bootstrap(d, outcome)
    print(f"\n{label}: n={len(d)}, mean outcome {d[outcome].clip(lower=0).mean():.2f}, "
          f"mean potential WAR {d.war_pot.mean():.2f}")
    for name, c, l, h in zip(design(d.head(1)).columns, model.coef_, lo, hi):
        print(f"  {name:>14} {_readable(name, c):>6}   90% {_readable(name, l)} to {_readable(name, h)}")


def kept(d: pd.DataFrame) -> np.ndarray:
    """The product of each draftee's KEPT factors (1 where a line is absent)."""
    return np.array([np.prod([f.get(k, 1.0) for k in KEPT]) for f in d.factors])


def balanced(d: pd.DataFrame, pred, balance: float) -> np.ndarray:
    return np.where(d.group == "hitter", pred, pred * balance)


def held_out(d: pd.DataFrame, outcome: str, fit_outcome: str, balance: float) -> pd.DataFrame:
    """Mean per class, leaving each class out of a fit on `fit_outcome`
    (pitchers x `balance`): rho and the mean `outcome` of the top k, for the
    board and the fit."""
    out = []
    for year in sorted(d["class"].unique()):
        train, test = d[d["class"] != year], d[d["class"] == year].copy()
        train = train[train[f"{fit_outcome}_settled"]]
        test = test[test[f"{outcome}_settled"]]
        test["fit"] = balanced(test, fit(train, fit_outcome).predict(design(test).values) * kept(test), balance)
        y = test[outcome].clip(lower=0)
        for key in ("board", "fit"):
            row = {"class": year, "key": key, "rho": spearmanr(test[key], y)[0]}
            row.update({f"top {k}": y[test[key].nlargest(k).index].mean() for k in TOP_K})
            out.append(row)
    return pd.DataFrame(out).groupby("key").mean().drop(columns="class")


def pitcher_shares(d: pd.DataFrame, key: str) -> list:
    """The pitchers' share of each rank bucket, ranking `key` within each class."""
    rank = d.groupby("class")[key].rank(ascending=False, method="first")
    return [float((d.group[rank.between(lo, hi)] != "hitter").mean()) for lo, hi in BUCKETS]


def side_balance(d: pd.DataFrame, pred: pd.Series) -> float:
    """The factor on pitchers' predictions that brings the bucket shares to
    50% on average."""
    lo, hi = 0.2, 5.0
    for _ in range(40):
        k = np.sqrt(lo * hi)
        shares = pitcher_shares(d.assign(x=balanced(d, pred, k)), "x")
        lo, hi = (k, hi) if np.mean(shares) < 0.5 else (lo, k)
    return float(np.sqrt(lo * hi))


def growth_design(d: pd.DataFrame) -> pd.DataFrame:
    """The growth odds' columns, on draft-day inputs; the reference draftee
    is a hitter, 20-21 at the draft, REFERENCE_WAR at potential, 0 readiness,
    normal makeup, REFERENCE_YEARS on. A pitcher's velocity (the top of his
    range, from 93), potential Stuff (from 45) and pitch count (from 3) are 0
    for hitters."""
    pitcher = (d.group != "hitter").astype(float)
    velo = pd.to_numeric(d.velo.astype(str).str.split("-").str[-1], errors="coerce").fillna(93)
    cols = {
        "log potential": np.log(d.war_pot.clip(lower=LOG_FLOOR) / REFERENCE_WAR),
        "readiness": d.readiness.clip(*READINESS_CLIP),
        "SP": (d.group == "SP").astype(float), "RP": (d.group == "RP").astype(float),
        "age 19-": (d.age <= 19).astype(float), "age 22+": (d.age >= 22).astype(float),
        "years": d.years - REFERENCE_YEARS,
    }
    for label, test in {**MAKEUP, "AD H": lambda d: d.ad == "H", "AD L": lambda d: d.ad == "L"}.items():
        cols[label] = test(d).astype(float)
    cols["velocity"] = pitcher * (velo - 93)
    cols["Stuff P / 10"] = pitcher * (pd.to_numeric(d.stuff, errors="coerce").fillna(45) - 45) / 10
    cols["pitches"] = pitcher * (pd.to_numeric(d.pitches, errors="coerce").fillna(3) - 3)
    return pd.DataFrame(cols, index=d.index)


def growth_table(d: pd.DataFrame, base: Path, league: str, cache: str = None) -> pd.DataFrame:
    """The draftee table joined to the ceiling panel: per draftee (his last
    class), `outgrows` on the panel (his latest ceiling) and `outgrows_a` on
    outcome A (his value now, once settled), plus adaptability and years on."""
    draftees, looks = ceiling_panel.load(base, league, cache)
    regular = ceiling_panel.regular_thresholds(base, league)
    o = ceiling_panel.outcomes(draftees, looks, regular, ceiling_panel._season(base, league))
    o = o.assign(id=o.id.astype(int))[["id", "class", "ad", "years", "outgrows", "g_now"]]
    g = d.merge(o, on=["id", "class"])
    g["outgrows_a"] = g.a_settled & (g.a >= g.war_pot + ceiling_panel.MARGIN) & (g.a >= g.g_now.map(regular))
    return g


def _growth_prior(names) -> tuple:
    """(means, sds) of the growth coefficients' priors: the GROWTH_JUDGMENT
    columns pinned near their odds, the rest shrunk to 0 as GROWTH_C sets."""
    mean = np.array([np.log(GROWTH_JUDGMENT[n]) if n in GROWTH_JUDGMENT else 0.0 for n in names])
    sd = np.array([JUDGMENT_SD if n in GROWTH_JUDGMENT else np.sqrt(GROWTH_C) for n in names])
    return mean, sd


def _map_logistic(x, y, mean, sd, offset=0.0) -> np.ndarray:
    """[intercept, coefficients] of a logistic fit, each coefficient with a
    normal prior (`mean`, `sd`); the intercept is free."""
    def loss(w):
        z = w[0] + x @ w[1:] + offset
        p = 1 / (1 + np.exp(-z))
        r = (w[1:] - mean) / sd
        value = -np.sum(y * z - np.logaddexp(0, z)) + 0.5 * np.sum(r ** 2)
        grad = np.concatenate([[np.sum(p - y)], x.T @ (p - y) + r / sd])
        return value, grad
    return optimize.minimize(loss, np.concatenate([[0.0], mean]), jac=True, method="L-BFGS-B").x


def fit_growth(g: pd.DataFrame, outcome: str, judgment=True) -> np.ndarray:
    """The growth odds: [intercept, coefficients] on `growth_design`."""
    x = growth_design(g)
    mean, sd = _growth_prior(x.columns)
    if not judgment:
        mean = np.zeros(len(mean))
        sd = np.full(len(sd), np.sqrt(GROWTH_C))
    return _map_logistic(x.values, g[outcome].values.astype(float), mean, sd)


def growth_logit(w, d: pd.DataFrame) -> np.ndarray:
    """The growth odds' log-odds for `d`, read REFERENCE_YEARS after the draft."""
    return w[0] + growth_design(d.assign(years=REFERENCE_YEARS)).values @ w[1:]


def report_growth(g: pd.DataFrame):
    panel = g[g["class"].isin(GROWTH_PANEL_CLASSES)]
    on_a = g[g["class"].isin(FIT_CLASSES) & g.a_settled]
    names = list(growth_design(g.head(1)).columns)
    fits = {}
    for label, sub, outcome, judgment in (("panel", panel, "outgrows", False), ("A", on_a, "outgrows_a", False),
                                          ("panel + judgment", panel, "outgrows", True)):
        rng = np.random.default_rng(0)
        boots = [fit_growth(sub.iloc[i], outcome, judgment)[1:]
                 for i in (rng.integers(0, len(sub), len(sub)) for _ in range(BOOTSTRAPS))]
        fits[label] = (fit_growth(sub, outcome, judgment)[1:], *np.percentile(boots, [5, 95], axis=0))
        if not judgment:
            print(f"  {label}: classes {sub['class'].min()}-{sub['class'].max()}, n={len(sub)}, "
                  f"outgrew {sub[outcome].mean():.1%} ({int(sub[outcome].sum())})")
    print(f"\n  {'odds of outgrowing':>18}" + "".join(f"  {label + ' (90%)':>24}" for label in fits))
    for i, name in enumerate(names):
        cells = [f"x{np.exp(w[i]):.2f} ({np.exp(lo[i]):.2f}-{np.exp(hi[i]):.2f})" for w, lo, hi in fits.values()]
        print(f"  {name:>18}" + "".join(f"  {c:>24}" for c in cells))
    print(f"  judgment: " + ", ".join(f"{n} x{v:.2f}" for n, v in GROWTH_JUDGMENT.items()))
    return fits


class Odds:
    """The three outcomes (B7): he outgrows his ceiling (the growth odds,
    borrowed from the panel and brought to outcome A's rate), or he doesn't,
    and then busts (A = 0) or lands short of it. Fit on outcome A's classes:

    - P(outgrows): the panel's growth odds with GROWTH_JUDGMENT, plus one
      shift fit on A - how often a ceiling that grows is realized
    - outgrowing, how far: A past ceiling + MARGIN, a gamma
    - otherwise: the Poisson mean of A, P(A > 0) by logistic regression, and
      A given A > 0 a gamma of that mean, its spread by side

    Everything scales with `scale` (the kept lines, and the balance on
    pitchers), as the board scales his value."""

    def fit(self, a: pd.DataFrame, a_all: pd.DataFrame, panel: pd.DataFrame):
        self.growth = fit_growth(panel, "outgrows")
        y = a_all.outgrows_a.values.astype(float)
        offset = growth_logit(self.growth, a_all)
        self.shift = float(_map_logistic(np.zeros((len(a_all), 0)), y, np.zeros(0), np.ones(0), offset)[0])
        grown = a[a.outgrows_a]
        excess = (grown.a - grown.war_pot - ceiling_panel.MARGIN).clip(lower=1e-3)
        self.excess = stats.gamma.fit(excess, floc=0)          # (shape, 0, scale)
        rest = a[~a.outgrows_a]
        x = design(rest).values
        self.mean = PoissonRegressor(alpha=ALPHA, max_iter=5000).fit(x, rest.a.clip(lower=0).values)
        self.sticks = LogisticRegression(C=1e4, max_iter=5000).fit(x, rest.a.values > 0)
        p, mu = self.sticks.predict_proba(x)[:, 1], self.mean.predict(x)
        pos = rest.a.values > 0
        resid = (rest.a.values[pos] - mu[pos] / p[pos]) / (mu[pos] / p[pos])
        self.shape = {g: 1 / np.mean(resid[rest.group.values[pos] == g] ** 2) for g in ("hitter", "SP", "RP")}
        return self

    def outgrows(self, d) -> np.ndarray:
        return 1 / (1 + np.exp(-(growth_logit(self.growth, d) + self.shift)))

    def parts(self, d, scale=1.0) -> dict:
        x = design(d).values
        p = self.sticks.predict_proba(x)[:, 1]
        mean = self.mean.predict(x)
        return {"q": self.outgrows(d), "p": p, "mean": mean * scale, "k": d.group.map(self.shape).values,
                "floor": (d.war_pot.values + ceiling_panel.MARGIN) * scale, "excess": self.excess[2] * scale}

    def expected(self, d, scale=1.0) -> np.ndarray:
        c = self.parts(d, scale)
        grown = c["floor"] + self.excess[0] * c["excess"]
        return (1 - c["q"]) * c["mean"] + c["q"] * grown

    def from_growth(self, d, scale=1.0) -> np.ndarray:
        """The part of E[v] the outgrowing outcome adds over the rest."""
        c = self.parts(d, scale)
        return c["q"] * (c["floor"] + self.excess[0] * c["excess"] - c["mean"])

    def cdf(self, d, v, scale=1.0) -> np.ndarray:
        c = self.parts(d, scale)
        theta = c["mean"] / c["p"] / c["k"]
        rest = (1 - c["p"]) + c["p"] * stats.gamma.cdf(v, c["k"], scale=theta)
        grown = stats.gamma.cdf(v - c["floor"], self.excess[0], scale=c["excess"])
        return np.where(v < 0, 0.0, (1 - c["q"]) * rest + c["q"] * grown)

    def quantile(self, d, q, scale=1.0) -> np.ndarray:
        lo, hi = np.zeros(len(d)), np.full(len(d), 40.0)
        for _ in range(50):
            mid = (lo + hi) / 2
            below = self.cdf(d, mid, scale) < q
            lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
        return np.where(self.cdf(d, np.zeros(len(d)), scale) >= q, 0.0, hi)


def report_odds(g: pd.DataFrame, regular: dict):
    """B7: the three outcomes, held out one class at a time, against the
    Poisson mean and the board."""
    able = g[g.war_pot >= MIN_POTENTIAL_WAR].assign(kept=lambda x: kept(x))
    a = able[able["class"].isin(FIT_CLASSES) & able.a_settled]
    a_all = g[g["class"].isin(FIT_CLASSES) & g.a_settled]
    panel = g[g["class"].isin(GROWTH_PANEL_CLASSES)]

    def scale(d, k):
        return d.kept.values * np.where(d.group == "hitter", 1.0, k)

    full = Odds().fit(a, a_all, panel)
    poisson = fit(a, "a")
    k_odds = side_balance(able, pd.Series(full.expected(able, scale(able, 1.0)), index=able.index))
    k_pois = side_balance(able, pd.Series(poisson.predict(design(able).values) * able.kept.values, index=able.index))
    print(f"  realized share of grown ceilings: x{np.exp(full.shift):.2f} on the odds; "
          f"how far past ceiling + {ceiling_panel.MARGIN:g}: mean {full.excess[0] * full.excess[2]:.2f} WAR")
    print(f"  pitcher balance: odds x{k_odds:.2f}, Poisson x{k_pois:.2f}")
    ev = full.expected(able, scale(able, k_odds))
    print(_shares_line("the odds", pitcher_shares(able.assign(x=ev), "x")))

    rows, pooled = [], []
    for year in sorted(a["class"].unique()):
        train, test = a[a["class"] != year], a[a["class"] == year]
        m = Odds().fit(train, a_all[a_all["class"] != year], panel[panel["class"] != year])
        sc = scale(test, k_odds)
        ev = m.expected(test, sc)
        y = test.a.clip(lower=0).values
        scores = {"board": test.board.values, "Poisson": fit(train, "a").predict(design(test).values) * scale(test, k_pois),
                  "the odds": ev}
        for key, s in scores.items():
            order = np.argsort(-s)
            rows.append({"key": key, "rho": spearmanr(s, y)[0], **{f"top {k}": y[order[:k]].mean() for k in TOP_K}})
        reg = test.group.map(regular).values
        top = np.zeros(len(test), bool)
        top[np.argsort(-ev)[:100]] = True
        pooled.append(pd.DataFrame({"y": y, "p90": m.quantile(test, 0.9, sc), "q": m.outgrows(test),
                                    "grew": test.outgrows_a.values, "p_reg": 1 - m.cdf(test, reg, sc), "reg": y >= reg,
                                    "war_pot": test.war_pot.values, "top100": top}))
    print("\n  held out, mean per class, judged on A:")
    print("\n".join("    " + line for line in pd.DataFrame(rows).groupby("key").mean().round(3).to_string().splitlines()))
    h = pd.concat(pooled)
    print(f"\n  above P90 (target 10%): all {(h.y > h.p90).mean():.0%}, top 100 {(h.y > h.p90)[h.top100].mean():.0%}")
    band = pd.cut(h.war_pot, [MIN_POTENTIAL_WAR, 1.5, 2.5, 4, 99])
    by = h.groupby(band, observed=True).apply(lambda x: f"{(x.y > x.p90).mean():.0%} | {x.p_reg.mean():.2f}/{x.reg.mean():.2f}")
    print("  by ceiling (above P90 | P(regular) pred/obs): " + "   ".join(f"{b}: {v}" for b, v in by.items()))
    for label, pred, obs in (("P(regular)", "p_reg", "reg"), ("P(outgrows)", "q", "grew")):
        dec = h.groupby(pd.qcut(h[pred].rank(method="first"), 10, labels=False)).agg(a=(pred, "mean"), b=(obs, "mean"))
        print(f"  {label} by decile, pred/obs: " + " ".join(f"{x:.2f}/{z:.2f}" for x, z in dec.values))
    share = full.from_growth(able, scale(able, k_odds)) / full.expected(able, scale(able, k_odds))
    print(f"\n  share of E[v] from outgrowing: median {np.median(share):.0%}, P90 {np.percentile(share, 90):.0%}")
    return full, able.assign(ev=full.expected(able, scale(able, k_odds)), growth=full.from_growth(able, scale(able, k_odds)))


def _shares_line(label, shares) -> str:
    cells = "  ".join(f"{lo}-{hi}: {s:4.0%}" for (lo, hi), s in zip(BUCKETS, shares))
    flag = "" if all(0.4 <= s <= 0.6 for s in shares) else "   <- outside 40-60%"
    return f"  {label:>22}  {cells}{flag}"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--table", help="cache the draftee table here (a .pkl); read it when it exists")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--panel", help="cache the ceiling panel here (a .pkl); read it when it exists")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    if not (base / "league_snapshots" / args.league / "players.csv").exists():
        sys.exit("No league snapshot to judge outcomes on.")

    if args.table and Path(args.table).exists():
        d = pd.read_pickle(args.table)
    else:
        d = draftee_table(base, args.league)
        if args.table:
            d.to_pickle(args.table)
    able = d[d.war_pot >= MIN_POTENTIAL_WAR]
    mature = able[able["class"].isin(FIT_CLASSES)]
    a, b = mature[mature.a_settled], mature[mature.b_settled]
    print(f"{len(d)} draftees, {len(able)} with {MIN_POTENTIAL_WAR}+ potential WAR; "
          f"fit on classes {FIT_CLASSES.start}-{FIT_CLASSES.stop - 1}")
    model_a, model_b = fit(a, "a"), fit(b, "b")
    report_fit("A: value now (the fit)", a, "a", model_a)
    report_fit(f"B: MLB WAR through {B_LAST_AGE} (the check)", b, "b", model_b)
    print(f"\nreference: hitter, 21 at the draft, {REFERENCE_WAR:g} WAR at potential, 0 WAR readiness, "
          "normal makeup (full weight)")

    pred = model_a.predict(design(able).values) * kept(able)
    balance = side_balance(able, pd.Series(pred, index=able.index))
    print(f"\npitcher share by rank within class, classes {able['class'].min()}-{able['class'].max()}:")
    shares = {"board": pitcher_shares(able, "board"),
              "fit": pitcher_shares(able.assign(x=pred), "x"),
              "fit, no judgment lines": pitcher_shares(able.assign(x=pred / kept(able)), "x"),
              "fit, balanced": pitcher_shares(able.assign(x=balanced(able, pred, balance)), "x")}
    for label, s in shares.items():
        print(_shares_line(label if label != "fit, balanced" else f"fit, pitchers x{balance:.2f}", s))

    print("\nheld out, one class at a time (mean per class), the fit with the judgment lines, balanced:")
    checks = {}
    for outcome, label in (("a", "A: value now"), ("b", f"B: MLB WAR to {B_LAST_AGE}")):
        table = held_out(mature, outcome, "a", balance)
        checks[outcome] = table.round(3).to_dict(orient="index")
        print(f"  judged on {label}, fit on A\n" + "\n".join("    " + line for line in table.round(3).to_string().splitlines()))

    print(f"\ngrowth odds: outgrowing the ceiling (+{ceiling_panel.MARGIN:g} WAR past draft day, and a regular):")
    g = growth_table(d, base, args.league, args.panel)
    report_growth(g)
    print("\nthe three outcomes (outgrows / short / bust), held out:")
    report_odds(g, ceiling_panel.regular_thresholds(base, args.league))

    names = list(design(able.head(1)).columns)
    coef = dict(zip(names, model_a.coef_))
    artifact = {
        "version": ARTIFACT,
        "outcome": "A: v2 full-time WAR on current ratings in the latest snapshot, 25+, 0 once gone",
        "min_potential_war": MIN_POTENTIAL_WAR,
        "log_floor": LOG_FLOOR,
        "reference_war": REFERENCE_WAR,
        # realized WAR = base x (potential WAR / reference) ^ exponent x the factors
        "base": round(float(np.exp(model_a.intercept_)), 5),
        "potential_exponent": round(float(coef["log potential"]), 4),
        "readiness": {"per_war": round(float(np.exp(coef["readiness"])), 4), "clip": list(READINESS_CLIP)},
        "role": {g: round(float(np.exp(coef[g])), 4) for g in ("SP", "RP")},
        # [youngest, oldest, factor at the reference]
        "age": {label: [lo, hi, round(float(np.exp(coef[f"age {label}"])), 4)]
                for label, (lo, hi) in AGE_GROUPS.items()},
        # [youngest, oldest, exponent]: the age factor x (potential WAR / reference) ^ exponent
        "age_by_potential": {label: [lo, hi, round(float(coef[f"age {label} x potential"]), 4)]
                             for label, (lo, hi) in AGE_BY_POTENTIAL.items()},
        "makeup": {label: round(float(np.exp(coef[label])), 4) for label in MAKEUP},
        "taper": [development.FULL_WEIGHT_WAR, development.TAPERED_WAR, development.TAPERED_WEIGHT],
        "pitcher_balance": round(balance, 4),
        "check": {"held_out": checks, "pitcher_share": {k: [round(x, 3) for x in v] for k, v in shares.items()},
                  "b_fit": {n: round(float(c), 4) for n, c in zip(names, model_b.coef_)}},
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "league": args.league,
            "fit_classes": [FIT_CLASSES.start, FIT_CLASSES.stop - 1],
            "draftees": {"a": len(a), "b": len(b)},
        },
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
