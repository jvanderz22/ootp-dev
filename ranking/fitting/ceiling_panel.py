"""The ceiling panel (plans/draft-odds-plan.md, B5): each draftee's ceiling -
his potential ratings' full-time WAR (ranking.profiles.CEILING) - on draft
day and at every later look: the league's prospect exports and the latest
snapshot.

    python -m ranking.fitting.ceiling_panel --data-dir fly_data [--cache panel.pkl]

A ceiling grows two ways the data can't tell apart - the ratings really grow,
or the scout's read was wrong and corrects upward - and for the board both are
upside nobody could see on draft day. A draftee **outgrows** his ceiling when,
at the latest look, it's MARGIN WAR or more past his draft-day one and at
least a regular's (decided 2026-11-10). A regular is valued on the full-time
scale (`regular_thresholds`).

Every class's export is scored, so a draftee who re-entered a later draft
keeps his last class (and only the looks after it).
"""
import argparse
import contextlib
import csv
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from context import default_base_dir

CLASSES = range(2033, 2042)
PROSPECT_YEARS = range(2038, 2043)
# where in its year each look falls, so they order: the draft (summer), the
# prospect export, the snapshot (November)
LOOK_OFFSET = {"draft": 0.0, "prospects": 0.5, "snapshot": 0.9}
MARGIN = 1.0
# a regular bullpen role: the median team's this-many-th best MLB reliever
BULLPEN = 8


def _ceilings(rows) -> dict:
    """{id: (ceiling WAR, "hitter" | "SP" | "RP")}: `rows` scored on CEILING."""
    from league_snapshot import coerce_gf
    from models.game_players import GamePlayer
    from ranking.profiles import CEILING
    from ranking.ranker import Ranker

    players = []
    for r in rows:
        # older exports carry only current velocity (see eval_rankings.read_classes)
        players.append(GamePlayer({**r, "G/F": coerce_gf(r.get("G/F")), "VT": r.get("VT") or r.get("VELO")}))
    with contextlib.redirect_stdout(io.StringIO()):
        ranked = Ranker(CEILING).rank(players, batch_size=max(len(players), 1))
    return {x.id: ((x.pre_demand_score - 50) / 10, "hitter" if x.ledger.side == "batting" else x.ledger.role)
            for x in ranked}


def _velocity(row) -> float:
    """The top of his velocity range ("94-96" -> 96); NaN when not exported."""
    try:
        return float(str(row.get("VT") or row.get("VELO")).split("-")[-1])
    except ValueError:
        return np.nan


def _looks(rows, year, source):
    scored = _ceilings(rows)
    for r in rows:
        if r["ID"] in scored:
            war, group = scored[r["ID"]]
            yield {"id": r["ID"], "look": year + LOOK_OFFSET[source], "source": source, "age": int(r["Age"]),
                   "ceiling": war, "group": group, "pot": pd.to_numeric(r.get("POT"), errors="coerce"),
                   "stuff_p": pd.to_numeric(r.get("STU P"), errors="coerce"), "velo": _velocity(r)}


def _prospects(base: Path, league: str, year: int):
    for d in (base / "datasets", Path("datasets")):
        path = d / f"{league}-{year}-prospects.csv"   # the own-scout file, not -osa
        if path.exists():
            with open(path, newline="") as f:
                return list(csv.DictReader(f))
    return []


def build(base: Path, league: str) -> tuple:
    """(draftees, looks): a row per draftee (his last class) with his draft-day
    makeup, and a row per look at him from his draft on."""
    from eval_rankings import read_classes, read_snapshot

    names = {f"{league}-{y}-draft" for y in CLASSES}
    draftees, looks = [], []
    for name, rows in read_classes([Path("datasets"), base / "datasets"], league, names).items():
        year = int(name.split("-")[1])
        looks += _looks(rows, year, "draft")
        draftees += [{"id": r["ID"], "class": year, "name": r["Name"], "pos": r["POS"], "draft_age": int(r["Age"]),
                      "we": r.get("WE"), "int": r.get("INT"), "ad": r.get("AD"), "prone": r.get("Prone")}
                     for r in rows]
        print(f"  {name}: {len(rows)}", file=sys.stderr)
    draftees = pd.DataFrame(draftees).drop_duplicates("id", keep="last")
    ids = set(draftees.id)
    for year in PROSPECT_YEARS:
        rows = [r for r in _prospects(base, league, year) if r.get("ID") in ids]
        looks += _looks(rows, year, "prospects")
        print(f"  {league}-{year}-prospects: {len(rows)} draftees", file=sys.stderr)
    snapshot = read_snapshot(base / "league_snapshots" / league / "players.csv")
    season = _season(base, league)
    looks += _looks([r for r in snapshot.values() if r["ID"] in ids], season, "snapshot")
    looks = pd.DataFrame(looks).merge(draftees[["id", "class"]], on="id")
    return draftees, looks[looks.look >= looks["class"]].drop(columns="class")


def _season(base: Path, league: str) -> int:
    import json

    return int(json.loads((base / "league_snapshots" / league / "meta.json").read_text())["league_date"][:4])


def regular_thresholds(base: Path, league: str) -> dict:
    """{"hitter" | "SP" | "RP": full-time WAR} a regular is worth: the league's
    prices for an everyday bat and a rotation spot (ranking/value.py), and for
    a reliever the median team's BULLPEN-th best MLB reliever on the full-time
    scale (the bullpen's prices are at its spots' leverage, not his talent's)."""
    from eval_rankings import read_snapshot
    from models.game_players import GamePlayer
    from ranking import get_ranker, value

    prices = value.replacement(league).prices
    pen = [r for r in read_snapshot(base / "league_snapshots" / league / "players.csv").values()
           if r.get("Lev") == "MLB" and r.get("POS") in ("RP", "CL")]
    with contextlib.redirect_stdout(io.StringIO()):
        ranked = get_ranker("full_time").rank([GamePlayer(r) for r in pen])
    org = {r["ID"]: r.get("snap_org_id") for r in pen}
    war = pd.DataFrame({"org": [org[x.id] for x in ranked], "war": [(x.pre_demand_score - 50) / 10 for x in ranked]})
    nth = war.groupby("org").war.apply(lambda s: s.nlargest(BULLPEN).min() if len(s) >= BULLPEN else np.nan)
    return {"hitter": float(prices["H"]), "SP": float(prices["SP"]), "RP": round(float(nth.median()), 3)}


def outcomes(draftees: pd.DataFrame, looks: pd.DataFrame, regular: dict, season: int) -> pd.DataFrame:
    """A row per draftee: his draft-day ceiling and role, the latest snapshot's
    (NaN once he's gone), and whether he outgrew it."""
    first = looks[looks.source == "draft"].sort_values("look").drop_duplicates("id")
    last = looks[looks.source == "snapshot"].drop_duplicates("id").set_index("id")
    out = draftees.merge(first[["id", "ceiling", "group", "pot", "stuff_p", "velo"]].rename(
        columns={"ceiling": "c0", "group": "g0", "pot": "pot0", "stuff_p": "stuff0", "velo": "velo0"}), on="id")
    out["c_now"], out["g_now"] = out.id.map(last.ceiling), out.id.map(last.group)
    out["gone"] = out.c_now.isna()
    out["years"] = season - out["class"]
    out["regular_now"] = ~out.gone & (out.c_now >= out.g_now.map(regular))
    out["low"] = out.c0 < out.g0.map(regular)
    out["outgrows"] = out.regular_now & (out.c_now >= out.c0 + MARGIN)
    return out


def load(base: Path, league: str, cache: str = None) -> tuple:
    """(draftees, looks), from `cache` (a .pkl) when it exists; built (and
    written there) otherwise."""
    if cache and Path(cache).exists():
        return pd.read_pickle(cache)
    built = build(base, league)
    if cache:
        pd.to_pickle(built, cache)
    return built


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    p.add_argument("--cache", help="cache the panel here (a .pkl); read it when it exists")
    args = p.parse_args(argv)
    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    draftees, looks = load(base, args.league, args.cache)
    regular = regular_thresholds(base, args.league)
    t = outcomes(draftees, looks, regular, _season(base, args.league))
    print(f"{len(draftees)} draftees, {len(looks)} looks {looks.groupby('source').size().to_dict()}")
    print("a regular (full-time WAR): " + ", ".join(f"{g} {w:.2f}" for g, w in regular.items()))
    settled = t[t.years >= 3]
    print(f"\nclasses {settled['class'].min()}-{settled['class'].max()} (3+ years on):")
    print(f"  low ceilings (below a regular on draft day) now regulars: {settled[settled.low].regular_now.mean():.1%}"
          f" of {settled.low.sum()}")
    print(f"  outgrew their ceiling (+{MARGIN:g} WAR and a regular): {settled.outgrows.mean():.1%}"
          f" ({settled.outgrows.sum()})")
    print("  by class: " + "  ".join(f"{c} {v:.1%}" for c, v in t.groupby("class").outgrows.mean().items()))


if __name__ == "__main__":
    main()
