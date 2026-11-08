"""Fit the fielding talent model (ranking/fielding_talent.py) and write its artifact.

    python -m ranking.fitting.fielding_talent --data-dir fly_data

Your grids are one scale across positions: they already put a 70 Range
outfielder higher at CF than at LF, because CF is worth more (decided
2026-11-08). So one line turns a floored grid score into fielding value, the
same at every position: value = intercept + slope x grid, in runs per season
including the position's adjustment. It is fit, innings-weighted, on MLB
fielders: their zone rating + framing per season at a position, plus that
position's adjustment, against their floored grid there. The best position is
then simply the highest grid, and is also the most valuable.

Per-position lines (each spread-matched to its own regulars) were tried first.
They valued a good CF more in LF, against the grids, and fit no better.

Position adjustments come from StatsPlus's own WAR: MLB hitter WAR split into
batting runs, fielding and baserunning runs, and an allowance per PA at each
position; an allowance minus the average of all nine (DH included), in runs.
"""
import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from context import default_base_dir
from ranking import bridge
from ranking.fielding_talent import (
    ARTIFACT, POSITIONS, SEASON_INNINGS, FieldingTalent, floored_grids, grid_scores, ratings_of,
)
from ranking.fitting.datasets import fielding_rows, season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.stats import DH, LEVEL_MLB, hitter_war, load_fielding
from ranking.hitter_talent import ARTIFACTS_DIR

SPREAD_YEARS = 8           # seasons of fielding stats behind each position's spread
SPREAD_LEVELS = (1, 2)     # MLB and AAA
SPREAD_MIN_INNINGS = 300
WAR_YEARS = 5
# 7. harder positions are worth more: (harder, easier) pairs of adjustments
POSITION_ORDER = [("C", "1B"), ("SS", "2B"), ("SS", "3B"), ("CF", "LF"), ("CF", "RF"),
                  ("2B", "1B"), ("3B", "1B"), ("LF", "1B"), ("RF", "1B"), ("1B", DH)]


def _players(path, ids=None):
    from models.game_players import GamePlayer

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["POS"] not in ("SP", "RP", "CL")]
    wanted = None if ids is None else {str(i) for i in ids}
    return [GamePlayer(r) for r in rows if wanted is None or r["ID"] in wanted]


def true_spreads(stats_dir, years) -> dict:
    """{position: (observed spread, season-to-season r, true spread)}, runs per season."""
    field = load_fielding(stats_dir, years)
    field = field[field.level_id.isin(SPREAD_LEVELS)]
    lines = field.groupby(["player_id", "year", "position"]).agg(ip=("ip", "sum"), runs=("runs", "sum"))
    lines = lines.reset_index()
    lines["rate"] = lines.runs / lines.ip * SEASON_INNINGS
    out = {}
    for pos in POSITIONS:
        p = lines[(lines.position == pos) & (lines.ip >= SPREAD_MIN_INNINGS)]
        mean = np.average(p.rate, weights=p.ip)
        observed = float(np.sqrt(np.average((p.rate - mean) ** 2, weights=p.ip)))
        pairs = p.assign(next=p.year + 1).merge(
            p, left_on=["player_id", "next"], right_on=["player_id", "year"], suffixes=("", "_next"))
        r = float(np.corrcoef(pairs.rate, pairs.rate_next)[0, 1])
        out[pos] = (observed, r, observed * np.sqrt(max(r, 0.0)))
    return out


def position_adjustments(stats_dir, years) -> dict:
    """{position: runs per season above the average position}, DH included."""
    war = hitter_war(stats_dir, years)
    allowance = war["allowance_600"]
    mean = np.mean(list(allowance.values()))
    return {n: round(float((a - mean) / war["per_defense_run"]), 2) for n, a in allowance.items()}, war["per_defense_run"]


def floored_by_season(rows, snapshots) -> dict:
    """{(season, player id): {position: floored grid score}}."""
    out = {}
    for season, path in snapshots.items():
        players = _players(path, rows[rows.season == season].player_id.unique())
        floored = floored_grids(grid_scores(players), ratings_of(players))
        for j, p in enumerate(players):
            out[season, int(p.id)] = {pos: float(floored[pos][j]) for pos in POSITIONS}
    return out


def fit_line(rows) -> tuple:
    """(intercept, slope) of runs per season plus the position's adjustment on
    the floored grid there, innings-weighted over every position."""
    w = np.sqrt(rows.ip.to_numpy(float))
    design = np.column_stack([np.ones(len(rows)), rows.grid])
    coef, *_ = np.linalg.lstsq(design * w[:, None], rows.value.to_numpy(float) * w, rcond=None)
    return float(coef[0]), float(coef[1])


def points_bridge(model: FieldingTalent, snapshot_path) -> dict:
    """Best-position value -> legacy best-position fielding points (before the
    utility bonus), matched by percentile over every hitter in the snapshot."""
    players = _players(snapshot_path)
    grids = grid_scores(players)
    value, _, _ = model.best(floored_grids(grids, ratings_of(players)))
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
    latest = max(sorted(int(f.stem) for f in (stats_dir / "field").glob("*.csv")))
    spreads = true_spreads(stats_dir, range(latest - SPREAD_YEARS + 1, latest + 1))
    adjustments, per_run = position_adjustments(stats_dir, range(latest - WAR_YEARS + 1, latest + 1))
    rows = fielding_rows(snapshots, stats_dir)
    rows = rows[(rows.level_id == LEVEL_MLB) & (rows.ip >= SPREAD_MIN_INNINGS)].copy()
    floored = floored_by_season(rows, snapshots)
    rows["grid"] = [floored[s, i][pos] for s, i, pos in zip(rows.season, rows.player_id, rows.position)]
    rows["per_season"] = rows.runs / rows.ip * SEASON_INNINGS
    rows["value"] = rows.per_season + rows.position.map(adjustments)
    intercept, slope = fit_line(rows)
    rows["line"] = intercept + slope * rows.grid
    print(f"value = {intercept:+.2f} + {slope:.3f} x grid   ({len(rows)} MLB position lines,"
          f" {SPREAD_MIN_INNINGS}+ innings); grid 0 {intercept:+.1f} vs DH {adjustments[DH]:+.1f}")

    print("\nposition  lines  adjustment   value: actual  line    spread: line  true   spearman(grid, runs)")
    report = {}
    for pos in POSITIONS:
        c = rows[rows.position == pos]
        actual, line = np.average(c.value, weights=c.ip), np.average(c.line, weights=c.ip)
        spread = slope * float(np.sqrt(np.average((c.grid - np.average(c.grid, weights=c.ip)) ** 2, weights=c.ip)))
        rho = float(spearmanr(c.grid, c.per_season).correlation)
        report[pos] = {"lines": len(c), "actual_value": round(actual, 1), "line_value": round(line, 1),
                       "line_spread": round(spread, 1), "true_spread": round(spreads[pos][2], 1),
                       "spearman_grid_runs": round(rho, 2)}
        print(f"  {pos:3}     {len(c):4}     {adjustments[pos]:+5.1f}        {actual:+5.1f}  {line:+5.1f}"
              f"          {spread:4.1f}  {spreads[pos][2]:4.1f}         {rho:5.2f}")
    print(f"  DH  adjustment {adjustments[DH]:+.1f}; WAR per fielding run {per_run:.3f}")

    order = [(a, b, adjustments[a] > adjustments[b]) for a, b in POSITION_ORDER]
    print("\nrule 7, harder positions are worth more:")
    for a, b, ok in order:
        print(f"  {'pass' if ok else 'FAIL'}  {a} ({adjustments[a]:+.1f}) > {b} ({adjustments[b]:+.1f})")

    artifact = {
        "version": ARTIFACT,
        "value_line": {"intercept": round(intercept, 3), "slope": round(slope, 4)},
        "position_adjustment": {pos: adjustments[pos] for pos in POSITIONS},
        "dh_adjustment": adjustments[DH],
    }
    artifact["points_bridge"] = points_bridge(FieldingTalent(artifact), snapshots[max(snapshots)])
    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "snapshot_seasons": sorted(snapshots),
        "spread_years": [latest - SPREAD_YEARS + 1, latest],
        "war_years": [latest - WAR_YEARS + 1, latest],
        "data_hash": data_hash(snapshots, stats_dir, range(latest - SPREAD_YEARS + 1, latest + 1),
                               kinds=("bat", "field")),
        "positions": report,
        "war_per_fielding_run": round(per_run, 4),
        "rules": {f"position order: {a} > {b}": {"passed": bool(ok)} for a, b, ok in order},
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
