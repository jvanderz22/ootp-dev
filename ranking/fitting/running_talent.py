"""Fit the baserunning talent model (ranking/running_talent.py) and write its artifact.

    python -m ranking.fitting.running_talent --data-dir fly_data

Extra bases: UBR per 600 PA as monotone parts in Speed and Baserunning plus a
level term. Steals: success rate (steals per attempt) and attempt rate
(attempts per time on first) from Stealing, each with a level term; the attempt
rate is then scaled up to what the most aggressive third of MLB teams ask of
runners of the same grade (optimal managing, decided 2026-11-08). Few
parameters each, and the opportunity-driven attempt counts only set one
multiplier.
"""
import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from context import default_base_dir
from ranking import bridge
from ranking.fitting.components import PARAMS, Additive, Rate
from ranking.fitting.datasets import read_fielders, running_rows, season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.stats import LEVEL_MLB, load_batting
from ranking.hitter_talent import ARTIFACTS_DIR
from ranking.running_talent import ARTIFACT, RunningTalent

SEASON_PA = 600
FOLDS = 5
REPORT_MIN_PA = 200
# runners this good at stealing are the ones whose usage the aggressive teams
# are judged on
AGGRESSIVE_MIN_STEAL = 55
AGGRESSIVE_SHARE = 1 / 3


def prepare(rows):
    return rows.assign(
        attempts=rows.sb + rows.cs,
        on_first=rows.single + rows.bb,
        extra_bases=rows.ubr / rows.pa * SEASON_PA,
    )


def fit_tables(rows) -> dict:
    steals = Rate(rows[rows.attempts > 0], "steal", "sb", "attempts", 1, ["level_id"])
    attempts = Rate(rows[rows.on_first > 0], "steal", "attempts", "on_first", 1, ["level_id"])
    extra = Additive(rows, ["speed", "running_ability"], "extra_bases", "pa", [1, 1], ["level_id"])
    return {
        "extra_bases": extra.tables(level_id=LEVEL_MLB),
        "steal_success": steals.table(level_id=LEVEL_MLB),
        "league_attempts": attempts.table(level_id=LEVEL_MLB),
    }


def aggressive_multiplier(stats_dir, snapshots, league_attempts) -> float:
    """Attempts the most aggressive third of MLB team-seasons got from good
    base stealers, over what the league curve expects of the same runners."""
    years = sorted({s for season in snapshots for s in (season, season - 1)})
    bat = load_batting(stats_dir, years)
    bat = bat[bat.level_id == LEVEL_MLB]
    players = read_fielders(snapshots[max(snapshots)])[["player_id", "steal"]]
    runners = bat.merge(players, on="player_id")
    runners = runners[runners.steal >= AGGRESSIVE_MIN_STEAL]
    runners = runners.assign(
        attempts=runners.sb + runners.cs,
        expected=np.asarray(league_attempts)[runners.steal.clip(20, 80) - 20] * (runners.single + runners.bb),
    )
    teams = runners.groupby(["team_id", "year"])[["attempts", "expected"]].sum()
    teams = teams[teams.expected > 0]
    teams["ratio"] = teams.attempts / teams.expected
    top = teams[teams.ratio >= teams.ratio.quantile(1 - AGGRESSIVE_SHARE)]
    return float(top.attempts.sum() / top.expected.sum())


def legacy_scores(players) -> dict:
    from attribute_models.running_attribute_model import RunningAttributeModel

    return dict(zip((int(p.id) for p in players), RunningAttributeModel().predict_many(players)))


def _players(path, ids=None):
    from models.game_players import GamePlayer

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["POS"] not in ("SP", "RP", "CL")]
    wanted = None if ids is None else {str(i) for i in ids}
    return [GamePlayer(r) for r in rows if wanted is None or r["ID"] in wanted]


def model_from(tables, base) -> RunningTalent:
    attempts = np.minimum(np.asarray(tables["league_attempts"]) * base["aggressive_multiplier"], 1.0)
    return RunningTalent({**base, **tables, "steal_attempts": np.round(attempts, 5).tolist()})


def report(rows, base, snapshots) -> dict:
    """Cross-validated, inside each level: the spearman of predicted with actual
    baserunning runs per PA, next to the legacy running model's. The actual
    runs reflect each manager's sends, so this measures the talent half."""
    oof = np.zeros(len(rows))
    for train, test in GroupKFold(FOLDS).split(rows, groups=rows.player_id):
        model = model_from(fit_tables(rows.iloc[train]), base)
        r = rows.iloc[test]
        oof[test] = model.runs({k: r[k].to_numpy() for k in ("speed", "steal", "running_ability")})
    legacy = {}
    for path in snapshots.values():
        legacy.update(legacy_scores(_players(path, rows.player_id.unique())))
    rows = rows.assign(predicted=oof, actual=rows.baserunning / rows.pa, legacy=rows.player_id.map(legacy))
    out = {}
    for level, group in rows[rows.pa >= REPORT_MIN_PA].groupby("level_id"):
        if len(group) >= 30:
            out[int(level)] = {
                "rows": len(group),
                "fitted": round(float(spearmanr(group.predicted, group.actual).correlation), 3),
                "legacy": round(float(spearmanr(group.legacy, group.actual).correlation), 3),
            }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir")
    p.add_argument("--snapshot", action="append", default=[], metavar="SEASON=PATH")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    base_dir = Path(args.data_dir) if args.data_dir else default_base_dir()
    stats_dir = base_dir / "league_stats" / args.league
    snapshots = season_snapshots(base_dir / "league_snapshots" / args.league,
                                 dict(s.split("=", 1) for s in args.snapshot))
    if not snapshots:
        sys.exit("No ratings snapshot: archive one, or pass --snapshot SEASON=PATH.")
    rows = prepare(running_rows(snapshots, stats_dir))
    tables = fit_tables(rows)
    bat = load_batting(stats_dir, [max(snapshots)])
    mlb = bat[bat.level_id == LEVEL_MLB]
    base = {
        "version": ARTIFACT,
        "aggressive_multiplier": round(aggressive_multiplier(stats_dir, snapshots, tables["league_attempts"]), 3),
        "times_on_first": round(float((mlb.single.sum() + mlb.bb.sum()) / mlb.pa.sum() * SEASON_PA), 1),
    }
    print(f"{len(rows)} rows; aggressive teams send good base stealers {base['aggressive_multiplier']}x"
          f" the league rate; {base['times_on_first']} times on first per {SEASON_PA} PA")
    cv = report(rows, base, snapshots)
    print("\ncross-validated spearman with baserunning runs per PA (200+ PA):\n  level  rows  fitted  legacy")
    for level, r in cv.items():
        print(f"  {level:>5} {r['rows']:>5}   {r['fitted']:.3f}   {r['legacy']:.3f}")

    model = model_from(tables, base)

    def show(**r):
        full = {"speed": 50, "steal": 50, "running_ability": 50, **r}
        one = {k: np.array([v]) for k, v in full.items()}
        return f"{float(model.extra_base_runs(one)[0]):+.1f} + {float(model.steal_runs(one)[0]):.1f}"

    print("\nruns per 600 PA (extra bases + steals), others at 50:")
    for v in (30, 40, 50, 60, 70, 80):
        print(f"  {v}:  speed {show(speed=v)}   steal {show(steal=v)}   baserunning {show(running_ability=v)}"
              f"   all three {show(speed=v, steal=v, running_ability=v)}")
    success = model.steal_success
    print("  steal success by Stealing:", {v: round(success[v - 20], 2) for v in (30, 40, 50, 60, 70, 80)})

    artifact = {**base, **tables, "steal_attempts": model.steal_attempts}
    players = _players(snapshots[max(snapshots)])
    ratings = {k: np.array([getattr(p, k) for p in players]) for k in ("speed", "steal", "running_ability")}
    legacy = list(legacy_scores(players).values())
    artifact["points_bridge"] = {
        "method": f"percentiles of {len(players)} snapshot hitters",
        **bridge.fit(model.runs(ratings), legacy),
    }
    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "snapshot_seasons": sorted(snapshots),
        "rows": len(rows),
        "data_hash": data_hash(snapshots, stats_dir, sorted({s for x in snapshots for s in (x, x - 1)})),
        "params": PARAMS,
        "cv_by_level": cv,
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
