"""Fit the hitter talent model (ranking/hitter_talent.py) and write its artifact.

    python -m ranking.fitting.hitter_talent --data-dir fly_data

Each component rate is fit on every level at once with a level term (see
ranking/fitting/components.py), weighted by its denominator; the artifact keeps
its MLB table.

The platoon mix - the share of PA each batting hand takes against left-handed
pitchers - is read off MLB lines' vs-L / vs-R PA; it blends a hitter's split
scores (ranking/hitter_talent.py). The batting hand is the latest snapshot's.
The expected splits - for a hitter without split ratings (potential ratings,
draft classes) - come from the latest snapshot's hitters: per batting hand
and rating, the weight OOTP's combined rating puts on vL, and vL - vR as a
line in the combined rating's level.

The report: cross-validated (folds grouped by player, so a player's seasons
stay together), the spearman of predicted runs per PA with the actual line
inside each level, next to the legacy batting model's on the same rows; then
the rules suite and the hypotheses. A new artifact replaces the committed one
only if both hold up and eval_rankings.py agrees.
"""
import argparse
import csv
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from context import default_base_dir
from ranking import bridge
from ranking.fitting import rules
from ranking.fitting.components import PARAMS, Rate
from ranking.fitting.datasets import hitter_rows, read_hitters, season_snapshots
from ranking.fitting.stats import (
    LEVEL_MLB, batting_pa_by_side, fit_linear_weights, load_batting, mlb_runs_per_pa, runs,
)
from ranking.hitter_talent import (
    ARTIFACT, ARTIFACTS_DIR, COMPONENTS, RATINGS, HitterTalent, outcomes, runs_per_pa,
)

# component -> (numerator, denominator, direction of its rating)
TARGETS = {
    "k": ("k", "pa", -1),
    "bb": ("bb", "pa", 1),
    "hr": ("hr", "contact", 1),
    "hit": ("hits_in_play", "in_play", 1),
    "xbh": ("extra_base", "hits_in_play", 1),
}
FOLDS = 5
REPORT_MIN_PA = 200


def fit_tables(rows) -> dict:
    return {
        name: Rate(rows, COMPONENTS[name], num, den, sign, ["level_id"]).table(level_id=LEVEL_MLB)
        for name, (num, den, sign) in TARGETS.items()
    }


def points_bridge(model: HitterTalent, snapshot_path) -> dict:
    """wRC+ -> legacy batting points, matched by percentile over every hitter in
    the snapshot (see ranking/bridge.py)."""
    hitters = read_hitters(snapshot_path)
    wrc = model.wrc_plus({r: hitters[r].to_numpy() for r in RATINGS})
    legacy = list(legacy_scores(snapshot_path, hitters.player_id).values())
    return {"method": f"percentiles of {len(hitters)} snapshot hitters", **bridge.fit(wrc, legacy)}


def triple_share(bat) -> float:
    mlb = bat[bat.level_id == LEVEL_MLB]
    return float(mlb.triple.sum() / (mlb.double.sum() + mlb.triple.sum()))


def predict_rows(model: HitterTalent, rows) -> np.ndarray:
    r = model.rates({rating: rows[rating].to_numpy() for rating in set(COMPONENTS.values())})
    events = outcomes(r["k"], r["bb"], r["hr"], r["hit"], r["xbh"], model.triple_share)
    return runs_per_pa(events, model.weights)


def legacy_scores(snapshot_path, player_ids) -> dict:
    """The legacy batting model's current-ratings score per player."""
    from attribute_models.batting_attribute_model import BattingAttributeModel
    from models.game_players import GamePlayer

    wanted = {str(i) for i in player_ids}
    opener = gzip.open if str(snapshot_path).endswith(".gz") else open
    with opener(snapshot_path, "rt", newline="") as f:
        players = [GamePlayer(r) for r in csv.DictReader(f) if r["ID"] in wanted]
    scores = BattingAttributeModel("overall").predict_many(players)
    return {int(p.id): s for p, s in zip(players, scores)}


def report(rows, artifact_base, snapshots) -> dict:
    """Cross-validated fitted vs legacy, inside each level."""
    oof = np.zeros(len(rows))
    for train, test in GroupKFold(FOLDS).split(rows, groups=rows.player_id):
        model = HitterTalent({**artifact_base, "tables": fit_tables(rows.iloc[train])})
        oof[test] = predict_rows(model, rows.iloc[test])
    rows = rows.assign(predicted=oof, actual=runs(rows, artifact_base["linear_weights"]) / rows.pa)
    legacy = {}
    for season, path in snapshots.items():
        legacy.update(legacy_scores(path, rows.player_id[rows.season == season].unique()))
    rows = rows.assign(legacy=rows.player_id.map(legacy))
    out = {}
    for level, group in rows[rows.pa >= REPORT_MIN_PA].groupby("level_id"):
        if len(group) < 30:
            continue
        out[int(level)] = {
            "rows": len(group),
            "fitted": round(float(spearmanr(group.predicted, group.actual).correlation), 3),
            "legacy": round(float(spearmanr(group.legacy, group.actual).correlation), 3),
        }
    return out


def data_hash(snapshots, stats_dir, years, kinds=("bat",)) -> str:
    digest = hashlib.sha256()
    paths = list(snapshots.values()) + [Path(stats_dir) / k / f"{y}.csv" for k in kinds for y in years]
    for path in paths:
        if Path(path).exists():
            digest.update(Path(path).read_bytes())
    return digest.hexdigest()[:12]


def platoon_mix(stats_dir, years, snapshot_path) -> dict:
    """{"R" | "L" | "S": share of PA against left-handed pitchers} over MLB
    hitters' lines."""
    lines = batting_pa_by_side(stats_dir, years)
    lines = lines[lines.level_id == LEVEL_MLB]
    snap = pd.read_csv(snapshot_path, low_memory=False, usecols=["ID", "B", "POS"])
    snap = snap[~snap.POS.isin(["SP", "RP", "CL"])]
    snap = snap.assign(bats=snap["B"].astype(str).str[:1].str.upper()).rename(columns={"ID": "player_id"})
    lines = lines.merge(snap[["player_id", "bats"]], on="player_id")
    out = {}
    for hand in ("R", "L", "S"):
        g = lines[lines.bats == hand]
        out[hand] = round(float(g.pa_l.sum() / (g.pa_l.sum() + g.pa_r.sum())), 4)
    return out


# rating -> its snapshot column, whose vL / vR splits are "<column> vL"
SPLIT_COLUMNS = {"babip": "BABIP", "avoid_k": "K's", "gap": "GAP", "power": "POW", "eye": "EYE"}
SPLIT_MIN_RATING = 25


def expected_splits(snapshot_path) -> dict:
    """{"R" | "L" | "S": {rating: {"weight", "gap": [at 50, per point]}}} from
    the snapshot's position players' combined and split ratings."""
    snap = pd.read_csv(snapshot_path, low_memory=False)
    snap = snap[~snap.POS.isin(["SP", "RP", "CL"])]
    bats = snap["B"].astype(str).str[:1].str.upper()
    out = {}
    for hand in ("R", "L", "S"):
        g = snap[bats == hand]
        out[hand] = {}
        for rating, col in SPLIT_COLUMNS.items():
            c, vl, vr = (pd.to_numeric(g[k], errors="coerce") for k in (col, f"{col} vL", f"{col} vR"))
            ok = c.notna() & vl.notna() & vr.notna() & (c >= SPLIT_MIN_RATING)
            c, d, vr = c[ok].to_numpy(float), (vl - vr)[ok].to_numpy(float), vr[ok].to_numpy(float)
            weight = float(np.linalg.lstsq(d[:, None], c - vr, rcond=None)[0][0])
            slope, at50 = np.polyfit(c - 50, d, 1)
            out[hand][rating] = {"weight": round(weight, 3), "gap": [round(float(at50), 3), round(float(slope), 4)]}
    return out


def pa_vs_lhp(stats_dir, years) -> float:
    """The share of MLB PA against left-handed pitchers - the short side of a
    platoon."""
    lines = batting_pa_by_side(stats_dir, years)
    lines = lines[lines.level_id == LEVEL_MLB]
    return round(float(lines.pa_l.sum() / (lines.pa_l.sum() + lines.pa_r.sum())), 4)


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
    rows = hitter_rows(snapshots, stats_dir)
    mix = platoon_mix(stats_dir, stat_years, snapshots[latest])
    print("share of PA against left-handed pitchers:", mix)
    splits = expected_splits(snapshots[latest])
    print("expected splits (weight on vL, vL - vR at 50 and per point):",
          {h: {r: (v["weight"], v["gap"]) for r, v in s.items()} for h, s in splits.items()})
    artifact_base = {
        "version": ARTIFACT,
        "linear_weights": {k: round(v, 4) for k, v in weights.items()},
        "triple_share": round(triple_share(bat[bat.year.isin(snapshots)]), 4),
        "platoon_mix": mix,
        "pa_vs_lhp": pa_vs_lhp(stats_dir, stat_years),
        "expected_splits": splits,
        "mlb_runs_per_pa": round(mlb_runs_per_pa(bat, weights, latest), 5),
    }
    print(f"{len(rows)} rows from seasons {sorted(rows.year.unique())}; "
          f"snapshots {sorted(snapshots)}; linear weights from {stat_years[0]}-{stat_years[-1]}")
    print("linear weights:", artifact_base["linear_weights"])

    cv = report(rows, artifact_base, snapshots)
    print(f"\ncross-validated spearman with runs per PA, rows with {REPORT_MIN_PA}+ PA:")
    print("  level   rows  fitted  legacy")
    for level, r in cv.items():
        print(f"  {level:>5} {r['rows']:>6}  {r['fitted']:.3f}   {r['legacy']:.3f}")

    artifact = {**artifact_base, "tables": fit_tables(rows)}
    artifact["points_bridge"] = points_bridge(HitterTalent(artifact), snapshots[latest])
    model = HitterTalent(artifact)

    def wrc(**ratings):
        return float(model.wrc_plus(ratings))

    results = rules.check_hitting(wrc)
    hypotheses = rules.check_hitting_hypotheses(wrc)
    print("\nrules suite:")
    for r in results:
        print(f"  {'pass' if r.passed else 'FAIL'}  {r.rule}: {r.detail}")
    print("hypotheses (reported, not enforced):")
    for r in hypotheses:
        print(f"  {'holds' if r.passed else 'not supported'}  {r.rule}: {r.detail}")
    print("\nbalanced anchors (grid -> fitted wRC+):",
          {f"{v}s": f"{rules.BALANCED_ANCHORS[v]} -> {w:.0f}" for v, w in rules.anchors(wrc).items()})

    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "snapshot_seasons": sorted(snapshots),
        "stat_years": stat_years,
        "rows": len(rows),
        "data_hash": data_hash(snapshots, stats_dir, stat_years),
        "params": PARAMS,
        "cv_by_level": cv,
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
