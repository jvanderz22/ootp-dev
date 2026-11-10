"""Fit each league's spots and what each costs (ranking/value.py's
`Replacement`, decided 2026-11-10) and write their artifact.

    python -m ranking.fitting.replacement --data-dir fly_data [--league yfmlb ...]

StatsPlus's WAR puts replacement where MLB's would be. This league's depth
puts it far higher: in November 2042, 58 free-agent starters valued at
1.5-2 WAR averaged 31 MLB innings the season before. So replacement here is
the league's own:

- the spots, measured on the stats league's latest season: the share of a
  full season the 8th-12th bats on a team get (by plate appearances), the
  leverage of bullpen spots 1-8 (a team's 8 busiest relievers by innings,
  ordered by their leverage per batter faced), and how far its managers
  moved those relievers' batters to their strong side (the share of
  same-or-opposite-handed batters he faced over what his hand faces, against
  his split - real or predicted - at FULL_TILT_SPLIT, fit through zero by
  TILT_GROUPS of spots: a closer pitches to whoever's due) - stored as the
  evidence for ranking/value.py's RELIEF_TILT, which you set
- the teams: the MLB organizations in each league's snapshot (distinct org
  ids with MLB-level players), so a 40-team league fits its own
- the prices: every non-amateur in the snapshot, scored on current ratings
  at each spot he can fill (model lines before any modifier), assigned to
  the league's spots for the most WAR - hitters to the lineups, pitchers to
  the rotations and bullpens. A spot's price is what one more of it would
  add (the assignment's shadow price): what the league's next-best player
  would add there.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from context import default_base_dir
from ranking.hitter_talent import ARTIFACTS_DIR
from ranking.value import (
    BULLPEN, DEFAULT_LEAGUE, FULL_TILT_SPLIT, LINEUP, LINEUP_FULL, RELIEF_TILT, REPLACEMENT_ARTIFACT,
    ROTATION, Replacement, load, spot_slots,
)
from scoring.runtime_components import runtime_components_scope

BATCH = 2000
# a player this far below StatsPlus's replacement at every spot never nears one
POOL_FLOOR = -1.0
# a bullpen spot is a team's relievers who start at most this share of their games
RELIEVER_STARTS = 0.2
# bullpen spots whose matchups are fit together (one spot is ~32 relievers)
TILT_GROUPS = ((1, 2), (3, 4), (5, 8))


def _rows(snapshot):
    with open(snapshot, newline="") as f:
        yield from csv.DictReader(f)


def teams(snapshot) -> int:
    """MLB organizations in the snapshot."""
    return len({r["snap_org_id"] for r in _rows(snapshot) if r.get("Lev") == "MLB" and r.get("snap_org_id")})


def _talent(snapshot, ids) -> dict:
    """{player id: (throws, his relief split)} for `ids`, as the talent stage
    reads his current ratings."""
    from league_snapshot import GamePlayer, coerce_gf
    from ranking.profiles import CURRENT
    from ranking.ratings import RatingsView
    from ranking.stages.talent import Talent
    from ranking.state import PlayerState

    rows = [r for r in _rows(snapshot) if r["ID"] in ids]
    for r in rows:
        r["G/F"] = coerce_gf(r.get("G/F"))
    with runtime_components_scope():
        states = [PlayerState(GamePlayer(r)) for r in rows]
        Talent(CURRENT).run(states, CURRENT)
    return {int(s.player.id): (RatingsView.throws(s.player), s.fitted["pitching"].rp_split)
            for s in states if s.fitted["pitching"] is not None}


def bullpen_tilt(pen: pd.DataFrame, pitch: pd.DataFrame, snapshot) -> list:
    """By bullpen spot, the share of a reliever's batters the managers moved
    to his strong side at FULL_TILT_SPLIT."""
    from ranking import pitcher_talent

    lefties = pitch[pitch.split_id == 2].groupby("player_id").bf.sum()
    pen = pen.assign(lhb=pen.player_id.map(lefties) / pen.bf)
    talent = _talent(snapshot, set(pen.player_id.astype(str)))
    pen = pen[pen.player_id.isin(talent)].copy()
    pen["throws"] = pen.player_id.map(lambda i: talent[i][0])
    pen["split"] = pen.player_id.map(lambda i: talent[i][1])
    mix = pitcher_talent.load().platoon_mix["rp"]
    pen = pen[pen.throws.isin(mix)].copy()
    usual = pen.throws.map(mix)
    # his own hand's batters, over what his hand usually faces; a positive
    # split is better against his own hand
    own = np.where(pen.throws == "L", pen.lhb - usual, usual - pen.lhb)
    pen["tilt"] = np.where(pen.split >= 0, own, -own)
    pen["ramp"] = (pen.split.abs() / FULL_TILT_SPLIT).clip(upper=1.0)
    out = [0.0] * BULLPEN
    for first, last in TILT_GROUPS:
        g = pen[pen.spot.between(first, last)]
        at_full = float(np.sum(g.bf * g.ramp * g.tilt) / np.sum(g.bf * g.ramp ** 2))
        for spot in range(first, last + 1):
            out[spot - 1] = round(max(at_full, 0.0), 4)
    return out


def measure_spots(stats_dir: Path, hitter_pa: float, snapshot) -> dict:
    """The lineup shares and the bullpen's leverage and matchups in the
    latest season's MLB stats (`snapshot`: the same league's ratings, for
    the relievers' splits)."""
    season = max(int(f.stem) for f in (stats_dir / "bat").glob("*.csv"))
    pitch_sides = pd.read_csv(stats_dir / "pitch" / f"{season}.csv")
    pitch_sides = pitch_sides[pitch_sides.level_id == 1]
    pitch = pitch_sides[pitch_sides.split_id == 1]
    bat = pd.read_csv(stats_dir / "bat" / f"{season}.csv")
    bat = bat[(bat.level_id == 1) & (bat.split_id == 1) & ~bat.player_id.isin(pitch.player_id)]

    pa = bat.groupby(["team_id", "player_id"]).pa.sum().reset_index()
    pa["bat"] = pa.groupby("team_id").pa.rank(ascending=False, method="first")
    by_bat = pa.groupby("bat").pa.mean()
    shares = [float(by_bat[k] / hitter_pa) for k in range(LINEUP_FULL + 1, LINEUP + 1)]

    pen = pitch.groupby(["team_id", "player_id"]).agg(g=("g", "sum"), gs=("gs", "sum"), outs=("outs", "sum"),
                                                     li=("li", "sum"), bf=("bf", "sum")).reset_index()
    pen = pen[(pen.gs <= RELIEVER_STARTS * pen.g) & (pen.bf > 0)]
    pen = pen[pen.groupby("team_id").outs.rank(ascending=False, method="first") <= BULLPEN].copy()
    pen["leverage"] = pen.li / pen.bf
    pen["spot"] = pen.groupby("team_id").leverage.rank(ascending=False, method="first")
    leverage = pen.groupby("spot").leverage.mean()
    return {"lineup_shares": [round(s, 3) for s in shares],
            "bullpen_leverage": [round(float(leverage[k]), 3) for k in range(1, BULLPEN + 1)],
            "bullpen_tilt": bullpen_tilt(pen, pitch_sides, snapshot),
            "season": season}


def spot_war(snapshot, spots: dict) -> tuple:
    """([{spot: WAR}] for hitters, [{spot: WAR}] for pitchers): every
    non-amateur in the snapshot on current ratings, at each spot he can fill
    on the side he's valued on, before modifiers."""
    from league_snapshot import GamePlayer, coerce_gf
    from ranking.profiles import CURRENT
    from ranking.stages.talent import Talent
    from ranking.stages.value import Value
    from ranking.state import PlayerState

    talent, value_stage = Talent(CURRENT), Value(CURRENT, replacement=Replacement(spots))
    hitters, pitchers = [], []

    def run(batch):
        with runtime_components_scope():
            states = [PlayerState(p) for p in batch]
            talent.run(states, CURRENT)
            value_stage.run(states, CURRENT)
        for s in states:
            side = s.batting if s.ledger.side == "batting" else s.pitching
            if side.spots:
                (hitters if side is s.batting else pitchers).append(side.spots)

    batch = []
    for row in _rows(snapshot):
        if row.get("is_amateur") == "1":
            continue
        row["G/F"] = coerce_gf(row.get("G/F"))
        batch.append(GamePlayer(row))
        if len(batch) >= BATCH:
            run(batch)
            batch = []
    if batch:
        run(batch)
    return hitters, pitchers


def prices(players: list, slots: dict) -> dict:
    """{spot: shadow price} with `players` ({spot: WAR} each) assigned to
    `slots` ({spot: count}) for the most WAR, at most one spot each."""
    names = list(slots)
    values = np.array([[p.get(s, -99.0) for s in names] for p in players])
    values = values[values.max(axis=1) > POOL_FLOOR]
    n, k = values.shape
    a = lil_matrix((n + k, n * k))
    for j in range(k):
        for i in range(n):
            a[i, j * n + i] = 1
        a[n + j, j * n:(j + 1) * n] = 1
    b = np.concatenate([np.ones(n), [slots[s] for s in names]])
    out = linprog(-values.T.ravel(), A_ub=a.tocsr(), b_ub=b, bounds=(0, 1), method="highs")
    if out.status != 0:
        sys.exit(f"spot assignment failed: {out.message}")
    return {s: round(float(-dual), 3) for s, dual in zip(names, out.ineqlin.marginals[n:])}


def fit_league(snapshot, spots: dict) -> dict:
    n_teams = teams(snapshot)
    slots = spot_slots(n_teams)
    hitters, pitchers = spot_war(snapshot, spots)
    lineup = {s: c for s, c in slots.items() if s.startswith("H")}
    staff = {s: c for s, c in slots.items() if not s.startswith("H")}
    return {"teams": n_teams, "prices": {**prices(hitters, lineup), **prices(pitchers, staff)},
            "players": {"hitters": len(hitters), "pitchers": len(pitchers)}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", action="append", help="league ids (default: every snapshot in the data dir)")
    p.add_argument("--stats-league", default=DEFAULT_LEAGUE, help="the league whose stats measure the spots")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--out", default=str(ARTIFACTS_DIR / f"{REPLACEMENT_ARTIFACT}.json"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    snapshots = base / "league_snapshots"
    spots = measure_spots(base / "league_stats" / args.stats_league, load().hitter_pa,
                          snapshots / args.stats_league / "players.csv")
    print("spots:", json.dumps(spots))
    leagues = args.league or sorted(d.name for d in snapshots.iterdir() if (d / "players.csv").exists())
    fitted = {}
    for league in leagues:
        fitted[league] = fit_league(snapshots / league / "players.csv", spots)
        print(league, json.dumps(fitted[league]))
    artifact = {
        "version": REPLACEMENT_ARTIFACT,
        "spots": spots,
        "leagues": fitted,
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats_league": args.stats_league,
            "judgment": {"lineup": [LINEUP_FULL, LINEUP], "rotation": ROTATION, "bullpen": BULLPEN,
                         "relief_tilt": RELIEF_TILT},
        },
    }
    if args.dry_run:
        return artifact
    Path(args.out).write_text(json.dumps(artifact, indent=1) + "\n")
    print(f"wrote {args.out}")
    return artifact


if __name__ == "__main__":
    main()
