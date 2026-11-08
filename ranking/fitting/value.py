"""Fit the value layer (ranking/value.py) and write its artifact.

    python -m ranking.fitting.value --data-dir fly_data

Everything is StatsPlus's own WAR taken apart, on MLB lines:

- hitters: WAR per batting run, per defense run, and the allowance per 600 PA
  (ranking.fitting.stats.hitter_war); the value layer uses the allowance
  averaged over the nine positions, since the fielding model's value already
  carries each position's adjustment against that average.
- pitchers: WAR per run saved against the league's ERA (FIP-based, as
  StatsPlus does) and per nine innings, for starters and relievers apart.
- full-time workloads (decided 2026-11-08): the median PA of hitters with
  502+, the median IP of relievers with 50+ games, and starters' innings per
  start by stamina (a line through MLB starters, 15+ starts) times the median
  starts of starters with 25+.
- leverage: relief seasons' leverage index per batter faced, given out by
  talent as an optimal manager would - the best reliever in the snapshot's
  MLB bullpens (scored as the talent stage scores him, splits and all) gets
  the top of the leverage distribution, and so on down.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from context import default_base_dir
from ranking.fitting.datasets import season_snapshots
from ranking.fitting.hitter_talent import data_hash
from ranking.fitting.pitcher_talent import _players
from ranking.fitting.stats import LEVEL_MLB, hitter_war, load_batting, load_pitching
from ranking.hitter_talent import ARTIFACTS_DIR
from ranking.stages.talent import PitcherTalent
from ranking.value import (
    ARTIFACT, LEVERAGE_WEIGHT, STARTER_MIN_PITCHES, STARTER_MIN_STAMINA, TWO_WAY_FLOOR, TWO_WAY_FULL, TWO_WAY_SHARE,
)
from scoring.runtime_components import runtime_components_scope

YEARS = 8                  # seasons of stats behind the WAR anatomy
QUALIFIED_PA = 502
FULL_TIME_RELIEF_GAMES = 50
FULL_TIME_STARTS = 25
STAMINA_FIT_STARTS = 15
RELIEF_MIN_IP = 30
STARTER_SHARE = 0.5
RELIEF_SHARE = 0.2
# leverage-map knots: talent percentiles among MLB relievers
LEVERAGE_KNOTS = np.linspace(0.01, 0.99, 50)


def pitching_lines(stats_dir, years) -> pd.DataFrame:
    pit = load_pitching(stats_dir, years)
    p = pit[pit.level_id == LEVEL_MLB].copy()
    p["ip"] = p.outs / 3
    p["role"] = np.where(p.gs >= STARTER_SHARE * p.g, "sp", np.where(p.gs <= RELIEF_SHARE * p.g, "rp", "sw"))
    p["li_bf"] = p.li / p.bf
    return p


def pitcher_war(p) -> dict:
    """Per role: WAR per run saved (FIP against the league ERA, x IP / 9) and
    per nine innings, fit on lines of 20+ IP."""
    lg = p[["er", "outs", "hr", "bb", "k"]].sum()
    lg_ip = lg.outs / 3
    lg_era = 9 * lg.er / lg_ip
    fip_c = lg_era - (13 * lg.hr + 3 * lg.bb - 2 * lg.k) / lg_ip
    p = p[p.ip >= 20].copy()
    p["saved"] = (lg_era - ((13 * p.hr + 3 * p.bb - 2 * p.k) / p.ip + fip_c)) * p.ip / 9
    out = {"league_era": float(lg_era)}
    sp = p[p.role == "sp"]
    coef, *_ = np.linalg.lstsq(np.column_stack([sp.saved, sp.ip / 9]), sp.war, rcond=None)
    out["sp"] = {"per_run": float(coef[0]), "per_nine": float(coef[1])}
    # relievers' WAR counts part of their leverage; split it out, so per_run is
    # a run saved at average leverage and the value layer adds its own
    rp = p[p.role == "rp"]
    coef, *_ = np.linalg.lstsq(np.column_stack([rp.saved, rp.saved * (rp.li_bf - 1), rp.ip / 9]), rp.war, rcond=None)
    out["rp"] = {"per_run": float(coef[0]), "per_nine": float(coef[2]),
                 "statsplus_leverage_weight": float(coef[1] / coef[0])}
    return out


def workloads(bat, p, snapshot_path) -> dict:
    hitters = bat[bat.level_id == LEVEL_MLB].groupby(["player_id", "year"]).pa.sum()
    seasons = p.groupby(["player_id", "year"]).agg(g=("g", "sum"), gs=("gs", "sum"), ip=("ip", "sum")).reset_index()
    relief = seasons[(seasons.gs <= RELIEF_SHARE * seasons.g) & (seasons.g >= FULL_TIME_RELIEF_GAMES)]
    snap = pd.read_csv(snapshot_path, low_memory=False, usecols=["ID", "STM"]).rename(columns={"ID": "player_id"})
    snap["STM"] = pd.to_numeric(snap.STM, errors="coerce")
    starts = seasons[(seasons.gs >= STAMINA_FIT_STARTS) & (seasons.gs >= 0.8 * seasons.g)].merge(snap, on="player_id")
    starts = starts.dropna(subset=["STM"])
    starts = starts[starts.year >= starts.year.max() - 1]   # the snapshot's stamina, its seasons
    slope, intercept = np.polyfit(starts.STM, starts.ip / starts.gs, 1, w=starts.gs)
    return {
        "hitter_pa": float(hitters[hitters >= QUALIFIED_PA].median()),
        "reliever_ip": float(relief.ip.median()),
        "starts": float(seasons[seasons.gs >= FULL_TIME_STARTS].gs.median()),
        "ip_per_start": {"intercept": round(float(intercept), 4), "per_stamina": round(float(slope), 5)},
        "stamina_fit_starters": int(len(starts)),
    }


def leverage_map(p, snapshot_path) -> dict:
    """{"runs_index": [...], "leverage": [...]}: a reliever's runs allowed index
    (as a reliever) -> the leverage he'd pitch at, by matching his talent
    percentile among the snapshot's MLB relievers to the same percentile of
    relief seasons' leverage (batters-faced weighted)."""
    relief = p[(p.role == "rp") & (p.ip >= RELIEF_MIN_IP)].sort_values("li_bf")
    cum = np.cumsum(relief.bf.to_numpy()) / relief.bf.sum()
    leverage = np.interp(LEVERAGE_KNOTS, cum, relief.li_bf.to_numpy())
    snap = pd.read_csv(snapshot_path, low_memory=False, usecols=["ID", "POS", "Lev"]).rename(columns={"ID": "player_id"})
    pen = snap[(snap.Lev == "MLB") & snap.POS.isin(["RP", "CL"])].player_id
    with runtime_components_scope():
        scored = PitcherTalent(SimpleNamespace(ratings="overall", rp_multiplier=1.0)).score(_players(snapshot_path, pen))
    index = np.array([f.rp_index for f in scored if f is not None])
    # the best reliever (lowest index) is the top percentile
    talent = np.quantile(index, 1 - LEVERAGE_KNOTS)
    order = np.argsort(talent)
    return {"runs_index": np.round(talent[order], 2).tolist(), "leverage": np.round(leverage[order], 3).tolist(),
            "relievers": int(len(index)), "relief_seasons": int(len(relief))}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    stats_dir = base / "league_stats" / args.league
    snapshots = season_snapshots(base / "league_snapshots" / args.league)
    if not snapshots:
        sys.exit("No ratings snapshot: archive one first.")
    snapshot = snapshots[max(snapshots)]
    latest = max(int(f.stem) for f in (stats_dir / "bat").glob("*.csv"))
    years = range(latest - YEARS + 1, latest + 1)

    hitters = hitter_war(stats_dir, years)
    lines = pitching_lines(stats_dir, years)
    pitchers = pitcher_war(lines)
    work = workloads(load_batting(stats_dir, years), lines, snapshot)
    leverage = leverage_map(lines, snapshot)
    allowance = float(np.mean(list(hitters["allowance_600"].values())))

    artifact = {
        "version": ARTIFACT,
        "hitter": {"per_batting_run": round(hitters["per_batting_run"], 5),
                   "per_defense_run": round(hitters["per_defense_run"], 5),
                   "allowance_600": round(allowance, 4)},
        "pitcher": {"league_era": round(pitchers["league_era"], 4),
                    **{role: {k: round(v, 5) for k, v in pitchers[role].items()} for role in ("sp", "rp")}},
        "workloads": work,
        "leverage": leverage,
    }
    ips = artifact["workloads"]["ip_per_start"]
    print(json.dumps({k: v for k, v in artifact.items() if k != "leverage"}, indent=1))
    print("starter IP by stamina:", {s: round(work["starts"] * (ips["intercept"] + ips["per_stamina"] * s))
                                     for s in (35, 40, 50, 60, 70, 80)})
    print("leverage by reliever runs index:", {round(i): round(l, 2) for i, l in
                                               zip(leverage["runs_index"][::7], leverage["leverage"][::7])})
    artifact["meta"] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": args.league,
        "stat_years": [years.start, years.stop - 1],
        "snapshot_season": max(snapshots),
        "data_hash": data_hash({max(snapshots): snapshot}, stats_dir, years, kinds=("bat", "pitch", "field")),
        "judgment": {"leverage_weight": LEVERAGE_WEIGHT, "two_way_share": TWO_WAY_SHARE,
                     "two_way_ramp_war": [TWO_WAY_FLOOR, TWO_WAY_FULL],
                     "starter_min_stamina": STARTER_MIN_STAMINA, "starter_min_pitches": STARTER_MIN_PITCHES},
    }
    if args.dry_run:
        return
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
