"""The evidence behind the development factors (ranking/development.py).

    python -m ranking.fitting.development --data-dir fly_data

Report only: the factors are judgment set from it, so nothing is written.
Every draftee of the league's past classes is scored by v2 on draft day
(potential and current ratings, model lines only - before any modifier) and
again on the latest snapshot: current ratings once he's ARRIVAL_AGE, potential
before, 0 WAR once he's gone (players who leave almost never had an MLB
career). A Poisson fit of max(outcome, 0) on draft-day potential WAR plus each
factor gives its multiplier; the same with career MLB WAR as the outcome, and
by potential-WAR band for the taper.

Age isn't fit into the factors: the outcomes disagree on it (value now meets
older draftees past their peak; career WAR gives college draftees more MLB
seasons in the window). Until the ratings archive can measure peak value it
stays on the legacy age table, balanced by the legacy draft-day current-ratings
modifiers.
"""
import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

from context import default_base_dir
from ranking import development

FIT_CLASSES = range(2033, 2037)       # old enough that most outcomes are settled
CAREER_CLASSES = range(2033, 2035)    # the longest career window
BANDS = [-np.inf, 1, 2.5, 4, np.inf]
FACTORS = {
    "WE H": lambda d: d.we == "H", "WE L": lambda d: d.we == "L",
    "INT H": lambda d: d["int"] == "H", "INT L": lambda d: d["int"] == "L",
    "Fragile": lambda d: d.prone.isin(["Fragile", "Wrecked"]),
    "Durable": lambda d: d.prone.isin(["Durable", "Iron Man"]),
}


def _raw_war(ranked) -> dict:
    """{id: WAR from the model lines alone}"""
    from ranking.ledger import MODEL

    out = {}
    for r in ranked:
        points = sum(line.delta for line in r.ledger.lines if line.stage == MODEL and r.ledger.counted(line))
        out[r.id] = (points - 50) / 10
    return out


def draftee_table(data_root: Path, league: str) -> pd.DataFrame:
    from eval_rankings import ARRIVAL_AGE, _class_players, read_classes, read_snapshot
    from models.game_players import GamePlayer
    from ranking import get_ranker

    snapshot = read_snapshot(data_root / "league_snapshots" / league / "players.csv")
    now = {
        "current": _raw_war(get_ranker("overall").rank([GamePlayer(r) for r in snapshot.values()])),
        "potential": _raw_war(get_ranker("potential").rank([GamePlayer(r) for r in snapshot.values()])),
    }
    classes = read_classes([Path("datasets"), data_root / "datasets"], league)
    rows = []
    for name, class_rows in classes.items():
        draft = _raw_war(get_ranker("draft_class").rank(_class_players(class_rows)))
        for r in class_rows:
            if r["ID"] not in draft:
                continue
            snap = snapshot.get(r["ID"])
            if snap is None:
                outcome = 0.0
            else:
                outcome = now["current" if int(snap["Age"]) >= ARRIVAL_AGE else "potential"][r["ID"]]
            rows.append({"class": int(name.split("-")[1]), "id": int(r["ID"]), "age": int(r["Age"]),
                         "we": r["WE"], "int": r["INT"], "prone": r["Prone"],
                         "war_pot": draft[r["ID"]], "outcome": outcome})
    return pd.DataFrame(rows)


def career_war(stats_dir) -> pd.Series:
    frames = []
    for kind in ("bat", "pitch"):
        for path in glob.glob(str(Path(stats_dir) / kind / "*.csv")):
            x = pd.read_csv(path, usecols=["player_id", "split_id", "level_id", "war"])
            frames.append(x[(x.split_id == 1) & (x.level_id == 1)])
    return pd.concat(frames).groupby("player_id").war.sum()


def multipliers(d: pd.DataFrame, outcome: str) -> dict:
    """{factor: multiplier on max(outcome, 0)}, potential WAR held fixed."""
    x = np.column_stack([d.war_pot.clip(-3, 8)] + [f(d).astype(float) for f in FACTORS.values()])
    fit = PoissonRegressor(alpha=1e-3, max_iter=3000).fit(x, d[outcome].clip(lower=0))
    return {name: round(float(np.exp(c)), 2) for name, c in zip(FACTORS, fit.coef_[1:])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league", default="yfmlb")
    p.add_argument("--data-dir", help="a DATA_DIR copy, e.g. fly_data (default: the app's)")
    args = p.parse_args(argv)
    base = Path(args.data_dir) if args.data_dir else default_base_dir()
    if not (base / "league_snapshots" / args.league / "players.csv").exists():
        sys.exit("No league snapshot to judge outcomes on.")

    d = draftee_table(base, args.league)
    d["career"] = d.id.map(career_war(base / "league_stats" / args.league)).fillna(0)
    fit = d[d["class"].isin(FIT_CLASSES)]
    career = d[d["class"].isin(CAREER_CLASSES)]
    print(f"{len(d)} draftees; fit on classes {FIT_CLASSES.start}-{FIT_CLASSES.stop - 1} ({len(fit)})\n")
    print("multipliers on what a draftee realizes, potential WAR held fixed:")
    print(f"  value now   {multipliers(fit, 'outcome')}")
    print(f"  career WAR  {multipliers(career, 'career')}  (classes {CAREER_CLASSES.start}-{CAREER_CLASSES.stop - 1})")
    print("\nby draft-day potential WAR (value now) - the taper:")
    for band, g in fit.groupby(pd.cut(fit.war_pot, BANDS), observed=True):
        print(f"  {str(band):12s} n={len(g):5d}  {multipliers(g, 'outcome')}")
    print("\nin use (ranking/development.py), full weight up to "
          f"{development.FULL_WEIGHT_WAR} WAR, {development.TAPERED_WEIGHT:.0%} from {development.TAPERED_WAR}:")
    for label, (_, table) in development.FACTORS.items():
        print(f"  {label}: {table}")


if __name__ == "__main__":
    main()
