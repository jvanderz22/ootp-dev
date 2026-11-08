"""Fit the pitcher talent model (ranking/pitcher_talent.py) and write its artifact.

    python -m ranking.fitting.pitcher_talent --data-dir fly_data

Each component rate is fit on every level at once with a level and a role
(starter / reliever) term (see ranking/fitting/components.py), weighted by its
denominator; the artifact keeps its MLB table for each role. `hr` and `hit`
are fit a second time on Movement, for classes exported without HRA / PBABIP.

Displayed Stuff is for the listed role (see ranking/pitcher_talent.py). The
role shift is fit from two exports of one org's pitchers, all set to SP and
all set to RP (`role_reference/all_starters.html`, `all_relievers.html` under
the data dir): reliever Stuff minus starter Stuff on the best four pitch
grades, current and potential each on their own grades. Its margin, taken off
on top when a reliever is scored as a starter, is the ROLE_SHIFT_MARGIN
quantile of what the formula misses (you'd rather take too much Stuff away
than too little, 2026-11-08). Before the rates are fit, each line's Stuff is
moved into the role he pitched (central shift, no margin).

PBABIP's effect is kept at PBABIP_KEEP of what the fit finds (decided
2026-11-08): MLB BABIP spread is about what luck alone gives, so the stats
can't size it, and you judge it to matter little. The `hit` tables (and the
Movement `hit` tables, which carry the same effect) are shrunk toward the MLB
average.

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
import pandas as pd
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from context import default_base_dir
from ranking import bridge
from ranking.fitting.components import PARAMS, Rate
from ranking.fitting import ootp_export, rules
from ranking.fitting.datasets import PITCH_COLUMNS, pitcher_rows, read_pitchers, season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.stats import (
    LEVEL_MLB, extra_base_shares, fit_linear_weights, load_batting, mlb_era, mlb_events_per_pa,
    mlb_runs_per_pa,
)
from ranking.hitter_talent import ARTIFACTS_DIR, HIGH, LOW, outcomes, runs_per_pa
from ranking.pitcher_talent import (
    ARTIFACT, COMPONENTS, MOVEMENT_COMPONENTS, ROLES, SHIFT_PITCHES, PitcherTalent, era_from, top_pitches,
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
# the share of the fitted PBABIP -> hits-in-play effect that is kept
PBABIP_KEEP = 1 / 3
ROLE_SHIFT_MARGIN = 0.75
# side -> (Stuff column, pitch grade columns) in an OOTP export
ROLE_SHIFT_SIDES = {
    "overall": ("STU", PITCH_COLUMNS),
    "potential": ("STU P", tuple(f"{c}P" for c in PITCH_COLUMNS)),
}
REPORT_MIN_BF = 150


def _tables(rows, components) -> dict:
    out = {role: {} for role in ROLES}
    for name, rating in components.items():
        num, den, sign = TARGETS[name]
        rate = Rate(rows, rating, num, den, sign, TERMS)
        for role in ROLES:
            out[role][name] = rate.table(level_id=LEVEL_MLB, sp=ROLE_SP[role])
    return out


def fit_role_shift(reference_dir) -> dict:
    """{side: {"coef", "margin", "pitchers", "rmse"}} from the all-SP and
    all-RP exports of the same pitchers."""
    starters = ootp_export.read(Path(reference_dir) / "all_starters.html")
    relievers = ootp_export.read(Path(reference_dir) / "all_relievers.html")
    pairs = starters.merge(relievers, on="ID", suffixes=("", "_rp"))
    out = {}
    for side, (stuff, grades) in ROLE_SHIFT_SIDES.items():
        values = pairs[list(grades)].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()
        top = np.array([top_pitches(g) for g in values], dtype=float)
        shift = pd.to_numeric(pairs[f"{stuff}_rp"], errors="coerce") - pd.to_numeric(pairs[stuff], errors="coerce")
        ok = shift.notna().to_numpy() & (top[:, 0] > 0)
        design = np.column_stack([np.ones(ok.sum()), top[ok]])
        coef, *_ = np.linalg.lstsq(design, shift[ok].to_numpy(float), rcond=None)
        missed = shift[ok].to_numpy(float) - design @ coef
        out[side] = {
            "coef": np.round(coef, 4).tolist(),
            "margin": round(float(np.quantile(missed, ROLE_SHIFT_MARGIN)), 2),
            "pitchers": int(ok.sum()),
            "rmse": round(float(np.sqrt(np.mean(missed ** 2))), 2),
        }
    return out


def in_line_role(rows, role_shift) -> pd.DataFrame:
    """Rows with Stuff moved into the role each line was pitched in."""
    coef = np.asarray(role_shift["overall"]["coef"])
    shift = np.maximum(coef[0] + rows[[f"p{i + 1}" for i in range(SHIFT_PITCHES)]].to_numpy(float) @ coef[1:], 0)
    stuff = rows.stuff + np.where((rows.sp == 1) & (rows.listed_sp == 0), -shift, 0)
    stuff = stuff + np.where((rows.sp == 0) & (rows.listed_sp == 1), shift, 0)
    return rows.assign(stuff=np.rint(stuff).astype(int))


def fit_tables(rows) -> dict:
    out = {
        "tables": _tables(rows, COMPONENTS),
        "movement_tables": _tables(rows, MOVEMENT_COMPONENTS),
    }
    mlb = rows[(rows.level_id == LEVEL_MLB) & (rows.in_play > 0)]
    for key, rating in (("tables", COMPONENTS["hit"]), ("movement_tables", MOVEMENT_COMPONENTS["hit"])):
        for role in ROLES:
            out[key][role]["hit"] = shrink(out[key][role]["hit"], mlb[rating], mlb.in_play)
    return out


def shrink(table, ratings, weights, keep=PBABIP_KEEP) -> list:
    """`table` pulled toward its average over the MLB rows, keeping `keep` of
    each rating's distance from it."""
    table = np.asarray(table)
    centre = np.average(table[np.clip(ratings.to_numpy(int), LOW, HIGH) - LOW], weights=weights)
    return (centre + keep * (table - centre)).round(5).tolist()


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
    top = pitchers[[f"p{i + 1}" for i in range(SHIFT_PITCHES)]].to_numpy()
    stuff = model.role_stuff(pitchers.stuff, top, pitchers.listed_sp, "overall")
    out = {}
    for role in ROLES:
        index = model.runs_index({**ratings, "stuff": stuff[role]}, role)
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
    p.add_argument("--role-reference", help="the all-SP / all-RP exports (default: <data dir>/role_reference)")
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
    reference = Path(args.role_reference) if args.role_reference else base / "role_reference"
    if not (reference / "all_starters.html").exists():
        sys.exit(f"No role exports under {reference}: save the all-SP / all-RP player lists there.")
    role_shift = fit_role_shift(reference)
    for side, f in role_shift.items():
        print(f"role shift ({side}, {f['pitchers']} pitchers): {f['coef']}, rmse {f['rmse']},"
              f" margin {f['margin']:+.2f} as a starter")
    rows = pitcher_rows(snapshots, stats_dir)
    moved = ((rows.sp == 1) != (rows.listed_sp == 1)).sum()
    rows = in_line_role(rows, role_shift)
    print(f"{moved} of {len(rows)} lines pitched outside the listed role; Stuff moved into it")
    artifact_base = {
        "version": ARTIFACT,
        "linear_weights": {k: round(v, 4) for k, v in weights.items()},
        "extra_base_share": round(extra_base, 4),
        "triple_share": round(triples, 4),
        "mlb_runs_per_pa": round(mlb_runs_per_pa(bat, weights, latest), 5),
        # the MLB average line's raw runs per nine -> the league's actual ERA
        "role_shift": role_shift,
        "era_scale": round(
            mlb_era(stats_dir, latest) / era_from(mlb_events_per_pa(bat, latest), weights, 1.0), 5
        ),
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

    def ra(stuff, control, movement, role, **parts):
        ratings = {"stuff": stuff, "control": control, "hra": movement, "pbabip": movement, **parts}
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

    def era(v, role):
        return float(model.era({"stuff": v, "control": v, "hra": v, "pbabip": v}, role))

    print(f"modeled ERA, balanced (SP | RP), MLB ERA {mlb_era(stats_dir, latest):.2f}:",
          {v: f"{era(v, 'sp'):.2f} | {era(v, 'rp'):.2f}" for v in (40, 50, 60, 70)})

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
