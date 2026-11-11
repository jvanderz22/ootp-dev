"""The prospect odds' table and the on-track description (plans/prospect-odds-plan.md,
"On track", step 1).

    python -m ranking.fitting.prospect_odds --data-dir fly_data [--table prospects.pkl] [--draftees draftees.pkl]

A row per prospect per export (2038-41, the own-scout files): his ceiling
(the potential profile's model lines) and readiness (FULL_TIME's), both on
the full-time scale as the draft fit has them, and outcome A on the latest
snapshot. Pooled with the draft fit's table (a draftee is a prospect on draft
day), it describes the gap - ceiling minus his WAR now - by age, and how much
of it players realize by how far ahead of the typical gap for their age they
are: whether POT - CUR should weigh differently by age.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from context import default_base_dir
from ranking.fitting import draft_odds
from ranking.fitting.ceiling_panel import _prospects

PROSPECT_YEARS = range(2038, 2042)
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
    rows = []
    for year in PROSPECT_YEARS:
        export = _prospects(base, league, year)
        # older exports carry only current velocity (as the ceiling panel reads them)
        players = [GamePlayer({**r, "G/F": coerce_gf(r.get("G/F")), "VT": r.get("VT") or r.get("VELO")})
                   for r in export]
        potential = draft_odds._raw_war(draft_odds._rank("potential", players))
        current = draft_odds._raw_war(draft_odds._rank("full_time", players))
        for r in export:
            pid = r["ID"]
            if pid not in potential or pid not in current:
                continue
            age, snap = int(r["Age"]), snapshot.get(pid)
            age_now = int(snap["Age"]) if snap else age + season - year
            rows.append({
                "source": "prospects", "class": year, "id": int(pid), "name": r["Name"], "pos": r["POS"],
                "age": age, "level": r.get("Lev"), "ovr": pd.to_numeric(r.get("OVR"), errors="coerce"),
                "we": r.get("WE"), "int": r.get("INT"), "prone": r.get("Prone"),
                "war_pot": potential[pid][0], "side": potential[pid][1], "role": potential[pid][2],
                "readiness": current[pid][0], "gone": snap is None, "age_now": age_now,
                "a": 0.0 if snap is None else now[pid][0], "a_settled": age_now >= ARRIVAL_AGE,
            })
        print(f"  {league}-{year}-prospects: {len(export)}", file=sys.stderr)
    d = pd.DataFrame(rows)
    d["group"] = np.where(d.side == "batting", "hitter", d.role)
    return d


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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--table", help="cache the prospect table here (a .pkl); read it when it exists")
    p.add_argument("--draftees", help="the draft fit's cached table (draft_odds --table)")
    args = p.parse_args(argv)
    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    if args.table and Path(args.table).exists():
        prospects = pd.read_pickle(args.table)
    else:
        prospects = prospect_table(base, args.league)
        if args.table:
            prospects.to_pickle(args.table)
    if args.draftees and Path(args.draftees).exists():
        draftees = pd.read_pickle(args.draftees)
    else:
        draftees = draft_odds.draftee_table(base, args.league)
    describe(pooled(prospects, draftees))


if __name__ == "__main__":
    main()
