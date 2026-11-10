"""Fit the fielding talent model (ranking/fielding_talent.py) and write its artifact.

    python -m ranking.fitting.fielding_talent --data-dir fly_data

Three parts (decided 2026-11-09; the research is in plans/xgboost-phaseout-plan.md,
step 2):

- **The tables.** For each position, runs per season against its average
  fielder, as a sum of one table per rating: monotone and piecewise-linear
  (knots at 40 / 50 / 60 / 70), fit on MLB and AAA lines (a level term keeps
  them on MLB's scale) - zone runs plus framing for every position, and double
  plays (DP_RUNS each) for 2B and SS on Turn DP. Each takes the strongest
  smoothing within 2% of the best out-of-fold error (folds grouped by player);
  the double plays keep the data's drop at 40-45 instead. Outside the 5-95%
  range of MLB regulars a table continues at its average slope inside it.
  Your judged tables (fielding_talent.JUDGED) replace the fit where they exist.
- **The position adjustments.** One per position, fit with a multinomial logit
  so the tables plus the adjustments reproduce where OOTP's managers play
  regulars (USAGE_INNINGS+ at their main position), pulled toward StatsPlus's
  own adjustments by PULL; SS then raised until TRUE_SHARE of MLB shortstops
  are worth the most at SS; and centred so the regulars' average matches
  StatsPlus's. StatsPlus's (from its WAR: an allowance per PA at each position
  against the average of all nine, DH included) put SS only 2 runs above 2B,
  so a true SS came out worth more at 2B.
- **The points bridge** from best-position value to legacy's best-position
  grid score, for the legacy scoring shell v2 still runs inside.
"""
import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear, minimize
from sklearn.model_selection import GroupKFold

from context import default_base_dir
from ranking import bridge
from ranking.fielding_talent import (
    ARTIFACT, JUDGED, POSITIONS, SEASON_INNINGS, STEPS, FieldingTalent, floor_factor, grid_scores, ratings_of,
)
from ranking.fitting.datasets import MIN_AGE, _join, _seasons, read_fielders, season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.stats import DH, LEVEL_MLB, hitter_war, load_fielding
from ranking.hitter_talent import ARTIFACTS_DIR

WAR_YEARS = 5
MIN_INNINGS = 300
LEVELS = (1, 2)            # MLB and AAA
KNOTS = (20, 40, 50, 60, 70, 80)
LAMBDAS = (0.3, 1, 3, 10, 30, 100, 300)
# the smoothing at least this strong for each position's main rating (2026-11-09:
# LF and RF went flat from Range 60 to 70, which looked like noise)
MIN_MAIN_LAMBDA = 30
# double plays keep the data's drop at 40-45 rather than smoothing it away
DP_LAMBDA = 0.3
# a double play instead of a force-out: run expectancy ~0.41 with no outs and
# 0.22 with one, ~0.31 on average, scaled to the league's 0.122 runs per PA
DP_RUNS = 0.33
READS = {
    "C": ("c_framing", "c_blocking", "c_arm"),
    "1B": ("if_range", "if_arm", "if_error"),
    "2B": ("if_range", "if_arm", "if_error"),
    "3B": ("if_arm", "if_range", "if_error"),
    "SS": ("if_range", "if_arm", "if_error"),
    "LF": ("of_range", "of_arm", "of_error"),
    "CF": ("of_range", "of_arm", "of_error"),
    "RF": ("of_range", "of_arm", "of_error"),
}
DP_POSITIONS = ("2B", "SS")
USAGE_INNINGS = 400
USAGE_YEARS = 2
# how hard the usage fit is pulled toward StatsPlus's adjustments (your call,
# 2026-11-09: "light" - 65% of regulars picked at their position, SS 13.5 runs
# above 2B, at most ~0.8 WAR from StatsPlus's at any position)
PULL = 0.1
# a true SS is worth the most at SS (your call, 2026-11-09): at least this
# share of MLB shortstops must be worth more there than at 2B or 3B. Not for
# CF: the centre fielders the usage fit moves to a corner are mostly Range
# 60-65, which your CF rule says can't start there.
TRUE_SHARE = 0.75
HARDER = {"SS": ("2B", "3B")}
# 7. harder positions are worth more: (harder, easier) pairs of adjustments
POSITION_ORDER = [("C", "1B"), ("SS", "2B"), ("SS", "3B"), ("CF", "LF"), ("CF", "RF"),
                  ("2B", "1B"), ("3B", "1B"), ("LF", "1B"), ("RF", "1B"), ("1B", DH)]


def _players(path, ids=None):
    from models.game_players import GamePlayer

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as f:
        snap = pd.read_csv(f, low_memory=False, dtype=str)
    snap = snap[~snap.POS.isin(["SP", "RP", "CL"])]
    if ids is not None:
        snap = snap[snap.ID.astype(int).isin(set(ids))]
    return [GamePlayer(r) for r in snap.fillna("").to_dict("records")]


# -- the tables --------------------------------------------------------------

def basis(ratings):
    r = np.asarray(ratings, float)
    return np.column_stack([np.clip(r - lo, 0, hi - lo) for lo, hi in zip(KNOTS[:-1], KNOTS[1:])])


def _design(rows, reads):
    return np.column_stack([np.ones(len(rows)), (rows.level_id != LEVEL_MLB).astype(float)]
                           + [basis(rows[r]) for r in reads])


def fit_tables(rows, y, reads, lam) -> np.ndarray:
    """Coefficients: intercept, the AAA level, then each rating's segment
    slopes (each >= 0), smoothed by `lam` on the change between segments."""
    X, w = _design(rows, reads), np.sqrt(rows.ip.to_numpy(float) / 1000)
    nseg = len(KNOTS) - 1
    smooth = []
    for k in range(len(reads)):
        for j in range(nseg - 1):
            row = np.zeros(X.shape[1])
            row[2 + k * nseg + j], row[2 + k * nseg + j + 1] = -1, 1
            smooth.append(np.sqrt(lam) * row)
    A = np.vstack([X * w[:, None], smooth])
    b = np.concatenate([y * w, np.zeros(len(smooth))])
    low = np.r_[-np.inf, -np.inf, np.zeros(X.shape[1] - 2)]
    return lsq_linear(A, b, bounds=(low, np.inf)).x


def out_of_fold(rows, y, reads, lam) -> float:
    """Innings-weighted out-of-fold RMSE on the MLB lines, folds by player."""
    err, total = 0.0, 0.0
    for train, test in GroupKFold(5).split(rows, y, rows.player_id.to_numpy()):
        coef = fit_tables(rows.iloc[train], y[train], reads, lam)
        test = test[rows.level_id.to_numpy()[test] == LEVEL_MLB]
        pred = _design(rows.iloc[test], reads) @ coef
        w = rows.ip.to_numpy(float)[test]
        err += float(np.sum(w * (y[test] - pred) ** 2))
        total += float(w.sum())
    return float(np.sqrt(err / total))


def seed(rows, y, reads, min_lambda=0.0) -> tuple:
    """(tables {rating: runs at STEPS, before centring}, lambda, out-of-fold RMSE)."""
    errors = {lam: out_of_fold(rows, y, reads, lam) for lam in LAMBDAS if lam >= min_lambda}
    best = min(errors.values())
    lam = max(lam for lam, e in errors.items() if e <= 1.02 * best)
    coef = fit_tables(rows, y, reads, lam)
    mlb = rows[rows.level_id == LEVEL_MLB]
    nseg = len(KNOTS) - 1
    tables = {}
    for k, r in enumerate(reads):
        slopes = coef[2 + k * nseg: 2 + (k + 1) * nseg]
        f = lambda x: float((basis([x]) @ slopes)[0])
        lo, hi = int(mlb[r].quantile(0.05)), int(mlb[r].quantile(0.95))
        slope = (f(hi) - f(lo)) / max(hi - lo, 1)
        tables[r] = np.array([f(lo) - slope * (lo - s) if s < lo else f(hi) + slope * (s - hi) if s > hi else f(s)
                              for s in STEPS])
    return tables, lam, errors[lam]


def position_tables(rows) -> tuple:
    """({position: {rating: runs at STEPS}}, report). Each position's tables
    sum to its MLB lines' innings-weighted actual runs on average: runs
    against its average fielder, as zone rating measures them."""
    out, report = {}, {}
    for pos, reads in READS.items():
        d = rows[rows.position == pos].reset_index(drop=True)
        tables, lam, rmse = seed(d, d.per_season.to_numpy(float), reads, MIN_MAIN_LAMBDA)
        if pos in DP_POSITIONS:
            coef = fit_tables(d, d.dp_runs.to_numpy(float), ("turn_dp",), DP_LAMBDA)
            dp = basis(STEPS) @ coef[2:]
            mlb = d[d.level_id == LEVEL_MLB]
            tables["turn_dp"] = dp - np.average(np.interp(mlb.turn_dp, STEPS, dp), weights=mlb.ip)
        mlb = d[d.level_id == LEVEL_MLB]
        for r in [r for r in tables if r != reads[0]]:
            tables[r] = tables[r] - np.average(np.interp(mlb[r], STEPS, tables[r]), weights=mlb.ip)
        predicted = sum(np.interp(mlb[r], STEPS, t) for r, t in tables.items())
        tables[reads[0]] = tables[reads[0]] + np.average(mlb.per_season - predicted, weights=mlb.ip)
        out[pos] = {r: np.round(t, 2).tolist() for r, t in tables.items()}
        report[pos] = {"lines": len(d), "mlb_lines": len(mlb), "lambda": lam, "rmse_out_of_fold": round(rmse, 2),
                       "rmse_none": round(float(np.sqrt(np.average((mlb.per_season - np.average(mlb.per_season, weights=mlb.ip)) ** 2, weights=mlb.ip))), 2)}
    return out, report


# -- the position adjustments ----------------------------------------------

def usage_adjustments(model: FieldingTalent, snapshot_path, stats_dir, season, war_adjustment) -> tuple:
    """({position: adjustment}, report): the logit fit of where managers play
    regulars, pulled toward `war_adjustment` and centred on its average."""
    field = load_fielding(stats_dir, range(season - USAGE_YEARS + 1, season + 1))
    field = field[field.level_id == LEVEL_MLB].groupby(["player_id", "year", "position"]).ip.sum().reset_index()
    main = field.sort_values("ip").groupby(["player_id", "year"]).tail(1)
    main = main[main.ip >= USAGE_INNINGS]
    players = _players(snapshot_path, main.player_id)
    index = {int(p.id): j for j, p in enumerate(players)}
    main = main[main.player_id.isin(index)]
    ratings = ratings_of(players)
    war = np.array([war_adjustment[p] for p in POSITIONS])
    # each position's runs, falling below its floors toward a DH's value (as
    # it would with an adjustment near StatsPlus's), before the adjustment
    runs = model.unfloored(ratings)
    floored = [floor_factor(p, ratings) * runs[p] + (1 - floor_factor(p, ratings)) * (model.dh_adjustment - war[k])
               for k, p in enumerate(POSITIONS)]
    R = np.column_stack(floored)[[index[i] for i in main.player_id]]
    y = np.array([POSITIONS.index(p) for p in main.position])

    def loglik(adj, temp):
        z = (R + adj) / temp
        z = z - z.max(axis=1, keepdims=True)
        return float(np.sum(z[np.arange(len(y)), y] - np.log(np.exp(z).sum(axis=1))))

    free = minimize(lambda t: -loglik(np.r_[0, t[:-1]], np.exp(t[-1])), np.r_[np.zeros(len(POSITIONS) - 1), np.log(5)],
                    method="L-BFGS-B")
    temp = float(np.exp(free.x[-1]))
    adj = minimize(lambda a: -loglik(a, temp) + PULL * np.sum((a - war) ** 2), war.copy(), method="L-BFGS-B").x
    raised = {}
    for hard, easier in HARDER.items():
        h = POSITIONS.index(hard)
        mine = R[y == h]
        need = max(adj[POSITIONS.index(e)] + np.quantile(mine[:, POSITIONS.index(e)] - mine[:, h], TRUE_SHARE)
                   for e in easier)
        raised[hard] = round(float(max(need - adj[h], 0.0)), 2)
        adj[h] = max(adj[h], need)
    adj = adj - np.average(adj[y], weights=main.ip) + np.average(war[y], weights=main.ip)
    picked = (R + adj).argmax(axis=1)
    picked_war = (R + war).argmax(axis=1)
    report = {"regular_seasons": int(len(y)), "temperature": round(temp, 2), "pull": PULL, "raised": raised,
              "picks_main_position": round(float(np.mean(picked == y)), 3),
              "picks_main_position_with_statsplus": round(float(np.mean(picked_war == y)), 3)}
    return {p: round(float(a), 2) for p, a in zip(POSITIONS, adj)}, report


def statsplus_adjustments(stats_dir, years) -> tuple:
    """({position: runs per season above the average position}, DH included;
    WAR per defense run), from StatsPlus's own WAR."""
    war = hitter_war(stats_dir, years)
    allowance = war["allowance_600"]
    mean = np.mean(list(allowance.values()))
    return {n: round(float((a - mean) / war["per_defense_run"]), 2) for n, a in allowance.items()}, war["per_defense_run"]


def points_bridge(model: FieldingTalent, snapshot_path) -> dict:
    """Best-position value -> legacy best-position fielding points (before the
    utility bonus), matched by percentile over every hitter in the snapshot."""
    players = _players(snapshot_path)
    value, _, _ = model.best(ratings_of(players))
    grids = grid_scores(players)
    legacy = np.column_stack([grids[pos] for pos in POSITIONS]).max(axis=1)
    return {"method": f"percentiles of {len(players)} snapshot hitters", **bridge.fit(value, legacy)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--snapshot", action="append", default=[], metavar="SEASON=PATH")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    stats_dir = base / "league_stats" / args.league
    snapshots = season_snapshots(base / "league_snapshots" / args.league,
                                 dict(s.split("=", 1) for s in args.snapshot))
    if not snapshots:
        sys.exit("No ratings snapshot: archive one, or pass --snapshot SEASON=PATH.")
    latest = max(int(f.stem) for f in (stats_dir / "field").glob("*.csv"))
    war_adjustment, per_run = statsplus_adjustments(stats_dir, range(latest - WAR_YEARS + 1, latest + 1))

    field = load_fielding(stats_dir, _seasons(snapshots))
    lines = field.groupby(["player_id", "year", "level_id", "position"])[["ip", "runs", "dp"]].sum().reset_index()
    rows = _join(snapshots, lines, read_fielders, MIN_AGE, MIN_INNINGS, "ip")
    rows = rows[rows.level_id.isin(LEVELS)].copy()
    rows["per_season"] = rows.runs / rows.ip * SEASON_INNINGS
    rows["dp_runs"] = rows.dp / rows.ip * SEASON_INNINGS * DP_RUNS
    tables, report = position_tables(rows)

    artifact = {
        "version": ARTIFACT,
        "steps": list(STEPS),
        "tables": tables,
        "position_adjustment": {pos: war_adjustment[pos] for pos in POSITIONS},
        "dh_adjustment": war_adjustment[DH],
    }
    snapshot = snapshots[max(snapshots)]
    adjustment, usage = usage_adjustments(FieldingTalent(artifact), snapshot, stats_dir, latest, war_adjustment)
    artifact["position_adjustment"] = adjustment
    # a first baseman is no worse than a DH, who fields nowhere
    artifact["position_adjustment"]["1B"] = max(adjustment["1B"], war_adjustment[DH])
    model = FieldingTalent(artifact)
    artifact["points_bridge"] = points_bridge(model, snapshot)

    adj = {**artifact["position_adjustment"], DH: war_adjustment[DH]}
    order = [(a, b, adj[a] > adj[b]) for a, b in POSITION_ORDER]
    print("position  lines (MLB)  smoothing  RMSE out of fold / none   adjustment: usage  StatsPlus")
    for pos in POSITIONS:
        r = report[pos]
        print(f"  {pos:3}    {r['lines']:4} ({r['mlb_lines']:3})   {r['lambda']:6}      {r['rmse_out_of_fold']:5.1f} / {r['rmse_none']:5.1f}"
              f"           {adj[pos]:+6.1f}   {war_adjustment[pos]:+6.1f}")
    print(f"  DH  {war_adjustment[DH]:+.1f}; judged tables: {', '.join(f'{p} {r}' for p, t in JUDGED.items() for r in t)}")
    print(f"usage: {usage['regular_seasons']} regular-seasons, temperature {usage['temperature']} runs, pull {PULL};"
          f" picks their main position {usage['picks_main_position']:.0%}"
          f" ({usage['picks_main_position_with_statsplus']:.0%} with StatsPlus's adjustments)")
    print("rule 7, harder positions are worth more:")
    for a, b, ok in order:
        print(f"  {'pass' if ok else 'FAIL'}  {a} ({adj[a]:+.1f}) > {b} ({adj[b]:+.1f})")

    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "snapshot_seasons": sorted(snapshots),
        "war_years": [latest - WAR_YEARS + 1, latest],
        "data_hash": data_hash(snapshots, stats_dir, _seasons(snapshots), kinds=("field",)),
        "positions": report,
        "statsplus_adjustment": war_adjustment,
        "usage": usage,
        "dp_runs": DP_RUNS,
        "war_per_fielding_run": round(per_run, 4),
        "rules": {f"position order: {a} > {b}": {"passed": bool(ok)} for a, b, ok in order},
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
