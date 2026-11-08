"""Fit the pitcher talent model (ranking/pitcher_talent.py) and write its artifact.

    python -m ranking.fitting.pitcher_talent --data-dir fly_data

Each component rate is fit on every level at once with a level and a role
(starter / reliever) term (see ranking/fitting/components.py), weighted by its
denominator; the artifact keeps its MLB table for each role. `hr` and `hit`
are fit a second time on Movement, for classes exported without HRA / PBABIP.

The report: cross-validated (folds grouped by player), the spearman of the
predicted runs allowed with the actual line inside each level and role - both
runs from the line's own events, and runs actually charged - next to the
legacy score for that role on the same rows; then the rules suite and the
hypotheses.
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
from ranking.fitting import rules
from ranking.fitting.components import PARAMS, Rate
from ranking.fitting.datasets import pitcher_rows, read_pitchers, season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.stats import (
    LEVEL_MLB, extra_base_shares, fit_linear_weights, load_batting, mlb_runs_per_pa,
)
from ranking.hitter_talent import ARTIFACTS_DIR, outcomes, runs_per_pa
from ranking.pitcher_talent import (
    ARTIFACT, COMPONENTS, MOVEMENT_COMPONENTS, ROLES, PitcherTalent,
)

# component -> (numerator, denominator, direction of its rating)
TARGETS = {
    "k": ("k", "bf", 1),
    "bb": ("bb", "bf", -1),
    "hr": ("hr", "contact", -1),
    "hit": ("hits_in_play", "in_play", -1),
}
ROLE_SP = {"sp": 1, "rp": 0}
TERMS = ["level_id", "sp"]
FOLDS = 5
REPORT_MIN_BF = 150


def _tables(rows, components) -> dict:
    out = {role: {} for role in ROLES}
    for name, rating in components.items():
        num, den, sign = TARGETS[name]
        rate = Rate(rows, rating, num, den, sign, TERMS)
        for role in ROLES:
            out[role][name] = rate.table(level_id=LEVEL_MLB, sp=ROLE_SP[role])
    return out


def fit_tables(rows) -> dict:
    return {
        "tables": _tables(rows, COMPONENTS),
        "movement_tables": _tables(rows, MOVEMENT_COMPONENTS),
    }


def predict_rows(model: PitcherTalent, rows) -> np.ndarray:
    """Runs allowed per BF for each row in its own role."""
    out = np.zeros(len(rows))
    ratings = {r: rows[r].to_numpy() for r in COMPONENTS.values()}
    for role in ROLES:
        mask = (rows.sp == ROLE_SP[role]).to_numpy()
        if mask.any():
            out[mask] = model.runs_index({r: v[mask] for r, v in ratings.items()}, role)
    return out * model.mlb_runs_per_pa / 100


def line_runs(rows, artifact) -> np.ndarray:
    """Runs per BF from a line's own events, its hits split at the MLB rate."""
    w, xbh, triples = artifact["linear_weights"], artifact["extra_base_share"], artifact["triple_share"]
    extra = rows.hits_in_play * xbh
    runs = (
        (rows.hits_in_play - extra) * w["single"]
        + extra * ((1 - triples) * w["double"] + triples * w["triple"])
        + rows.hr * w["hr"] + rows.bb * w["bb"] + rows.k * w["k"]
        + (rows.in_play - rows.hits_in_play) * w["out"]
    )
    return (runs / rows.bf).to_numpy()


def _players(snapshot_path, player_ids):
    from models.game_players import GamePlayer

    wanted = {str(i) for i in player_ids}
    opener = gzip.open if str(snapshot_path).endswith(".gz") else open
    with opener(snapshot_path, "rt", newline="") as f:
        return [GamePlayer(r) for r in csv.DictReader(f) if r["ID"] in wanted]


def legacy_scores(players) -> dict:
    """The legacy current-ratings (starter, reliever) scores per player."""
    from scoring.pitcher_scorer import PitcherScorer
    from scoring.runtime_components import runtime_components_scope

    with runtime_components_scope():
        scores = PitcherScorer("overall").score_many(players)
    return {int(p.id): (s[1], s[2]) for p, s in zip(players, scores)}


def points_bridges(model: PitcherTalent, snapshot_path) -> dict:
    """Runs allowed index -> legacy points, per role, matched by percentile over
    every pitcher in the snapshot (see ranking/bridge.py). The legacy side is
    the role score with the role factor the v2 stage multiplies back in taken
    out, so v2's role scores are spread as legacy's are."""
    from ranking.stages.talent import rp_role_factor, sp_role_factor
    from scoring.pitcher_scorer import RP_OVERALL_MODIFIER

    pitchers = read_pitchers(snapshot_path)
    players = {int(p.id): p for p in _players(snapshot_path, pitchers.player_id)}
    legacy = legacy_scores(list(players.values()))
    ratings = {r: pitchers[r].to_numpy() for r in COMPONENTS.values()}
    out = {}
    for role in ROLES:
        index = model.runs_index(ratings, role)
        talent, target = [], []
        for pid, value in zip(pitchers.player_id, index):
            p = players[pid]
            pitches = len(p.get_ovr_pitches())
            if role == "sp":
                factor = sp_role_factor(p.stamina, pitches)
                score = legacy[pid][0]
            else:
                factor = rp_role_factor(p.stamina, pitches) * RP_OVERALL_MODIFIER
                score = legacy[pid][1]
            if factor > 0:
                talent.append(value)
                target.append(score / factor)
        out[role] = {
            "method": f"percentiles of {len(talent)} snapshot pitchers",
            **bridge.fit(talent, target, higher_is_better=False),
        }
    return out


def report(rows, artifact_base, snapshots) -> dict:
    """Cross-validated fitted vs legacy, inside each level and role."""
    oof = np.zeros(len(rows))
    for train, test in GroupKFold(FOLDS).split(rows, groups=rows.player_id):
        model = PitcherTalent({**artifact_base, **fit_tables(rows.iloc[train])})
        oof[test] = predict_rows(model, rows.iloc[test])
    legacy = {}
    for season, path in snapshots.items():
        legacy.update(legacy_scores(_players(path, rows.player_id[rows.season == season].unique())))
    role_score = [legacy[p][0] if sp else legacy[p][1] for p, sp in zip(rows.player_id, rows.sp)]
    rows = rows.assign(
        predicted=oof, line=line_runs(rows, artifact_base), charged=rows.r / rows.bf, legacy=role_score,
    )
    out = {}
    for (level, sp), group in rows[rows.bf >= REPORT_MIN_BF].groupby(["level_id", "sp"]):
        if len(group) < 40:
            continue

        def rho(score, actual):
            # higher score = fewer runs
            return round(float(spearmanr(score, -group[actual]).correlation), 3)

        out[f"{int(level)} {'SP' if sp else 'RP'}"] = {
            "rows": len(group),
            "fitted": [rho(-group.predicted, "line"), rho(-group.predicted, "charged")],
            "legacy": [rho(group.legacy, "line"), rho(group.legacy, "charged")],
        }
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--snapshot", action="append", default=[], metavar="SEASON=PATH",
                   help="a ratings snapshot for SEASON, on top of the archived ones")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = p.parse_args(argv)

    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    stats_dir = base / "league_stats" / args.league
    extra = dict(s.split("=", 1) for s in args.snapshot)
    snapshots = season_snapshots(base / "league_snapshots" / args.league, extra)
    if not snapshots:
        sys.exit("No ratings snapshot with BABIP: archive one, or pass --snapshot SEASON=PATH.")
    stat_years = sorted(int(f.stem) for f in (stats_dir / "bat").glob("*.csv"))

    bat = load_batting(stats_dir, stat_years)
    weights = fit_linear_weights(bat)
    latest = max(snapshots)
    extra_base, triples = extra_base_shares(bat, snapshots)
    rows = pitcher_rows(snapshots, stats_dir)
    artifact_base = {
        "version": ARTIFACT,
        "linear_weights": {k: round(v, 4) for k, v in weights.items()},
        "extra_base_share": round(extra_base, 4),
        "triple_share": round(triples, 4),
        "mlb_runs_per_pa": round(mlb_runs_per_pa(bat, weights, latest), 5),
    }
    print(f"{len(rows)} rows from seasons {sorted(rows.year.unique())}; snapshots {sorted(snapshots)}")

    cv = report(rows, artifact_base, snapshots)
    print(f"\ncross-validated spearman with runs allowed per BF (from the line's events | charged),"
          f" rows with {REPORT_MIN_BF}+ BF:")
    print("  level role  rows   fitted         legacy")
    for key, r in cv.items():
        print(f"  {key:>10} {r['rows']:>5}   {r['fitted'][0]:.3f} | {r['fitted'][1]:.3f}"
              f"  {r['legacy'][0]:.3f} | {r['legacy'][1]:.3f}")

    artifact = {**artifact_base, **fit_tables(rows)}
    artifact["points_bridges"] = points_bridges(PitcherTalent(artifact), snapshots[latest])
    model = PitcherTalent(artifact)

    def ra(stuff, control, movement, role):
        ratings = {"stuff": stuff, "control": control, "hra": movement, "pbabip": movement}
        return float(model.runs_index(ratings, role))

    results = rules.check_pitching(ra)
    hypotheses = rules.check_pitching_hypotheses(ra)
    print("\nrules suite:")
    for r in results:
        print(f"  {'pass' if r.passed else 'FAIL'}  {r.rule}: {r.detail}")
    print("hypotheses (reported, not enforced):")
    for r in hypotheses:
        print(f"  {'holds' if r.passed else 'not supported'}  {r.rule}: {r.detail}")
    print("\nruns allowed index, balanced (SP | RP):",
          {v: f"{ra(v, v, v, 'sp'):.0f} | {ra(v, v, v, 'rp'):.0f}" for v in (40, 50, 60, 70)})

    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "snapshot_seasons": sorted(snapshots),
        "stat_years": stat_years,
        "rows": len(rows),
        "data_hash": data_hash(snapshots, stats_dir, stat_years, kinds=("bat", "pitch")),
        "params": PARAMS,
        "cv_by_level_role": cv,
        "rules": {r.rule: {"passed": r.passed, "detail": r.detail} for r in results},
        "hypotheses": {r.rule: {"holds": r.passed, "detail": r.detail} for r in hypotheses},
    }
    if args.dry_run:
        return
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
