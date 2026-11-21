"""Track a few draftees on the v2 draft board as the model changes.

    python print_draft_watch.py [--data-dir fly_data] [--save LABEL] [--against LABEL] [--ceiling-weight W]

Reads draft_watchlist.csv (dataset, id, name, note); each dataset is a class
export in the data dir's datasets/ (default fly_data, the local copy of the
live data), else ./datasets. For each player: his rank
before demand, his value and ceiling (WAR), the card's likely range and the
lines between his ceiling and his value. `--save` keeps this run under
draft_watch/LABEL.json; `--against` shows each player's rank and value from
a saved run beside today's. `--ceiling-weight` re-ranks on value^(1-W) x
ceiling^W, to try an upside weight without changing the board.
"""
import argparse
import contextlib
import csv
import io
import json
from pathlib import Path

from league_snapshot import coerce_gf
from models.game_players import GamePlayer
from ranking import get_ranker
from ranking.ledger import DEVELOPMENT, MODIFIERS
from ranking.value import DISPLAY_OFFSET, DISPLAY_SCALE

ROOT = Path(__file__).parent
WATCHLIST = ROOT / "draft_watchlist.csv"
SAVED = ROOT / "draft_watch"
# the lines worth a column, in ledger order, as the card labels them
SHOWN = ("Glove", "Base rate", "Readiness", "Polish", "Work ethic", "Intelligence", "Breakout", "Playing time",
         "velocity", "pitcher balance")


def _dataset(name, data_dir) -> Path:
    for folder in (Path(data_dir) / "datasets", ROOT / "datasets"):
        if (folder / name).exists():
            return folder / name
    raise SystemExit(f"{name}: not in {data_dir}/datasets or ./datasets")


def board(path: Path, weight: float) -> dict:
    """{id: (rank, result)} for a class, ranked before demand - or on value
    and ceiling blended by `weight`."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    players = [GamePlayer({**r, "G/F": coerce_gf(r.get("G/F"))}) for r in rows]
    with contextlib.redirect_stdout(io.StringIO()):
        ranked = get_ranker("draft_class").rank(players, batch_size=max(len(players), 1))
    if not weight:
        return {r.id: (r.pre_demand_rank, r) for r in ranked}
    score = {r.id: max(value(r), 1e-6) ** (1 - weight) * max(r.ceiling_war or 0.0, 0.5) ** weight for r in ranked}
    order = sorted(ranked, key=lambda r: score[r.id], reverse=True)
    return {r.id: (i + 1, r) for i, r in enumerate(order)}


def value(r) -> float:
    return (r.pre_demand_score - DISPLAY_OFFSET) / DISPLAY_SCALE


def lines(r) -> dict:
    out = {}
    for line in r.ledger.lines:
        if r.ledger.counted(line) and line.stage in (DEVELOPMENT, MODIFIERS) and line.label in SHOWN:
            out[line.label] = line.stat or f"{line.delta / DISPLAY_SCALE:+.2f}"
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", default=str(ROOT / "fly_data"))
    p.add_argument("--save", help="keep this run under draft_watch/LABEL.json")
    p.add_argument("--against", help="show a saved run's rank and value beside today's")
    p.add_argument("--ceiling-weight", type=float, default=0.0)
    args = p.parse_args(argv)
    with open(WATCHLIST, newline="") as f:
        entries = list(csv.DictReader(f))
    before = json.loads((SAVED / f"{args.against}.json").read_text()) if args.against else {}
    boards, saved = {}, {}
    for e in entries:
        if e["dataset"] not in boards:
            boards[e["dataset"]] = board(_dataset(e["dataset"], args.data_dir), args.ceiling_weight)
        found = boards[e["dataset"]].get(e["id"])
        if not found:
            print(f"{e['name']}: not in {e['dataset']}")
            continue
        rank, r = found
        row = {"rank": rank, "value": round(value(r), 2), "ceiling": round(r.ceiling_war or 0.0, 2),
               "range": [r.war_low, r.war_high], "lines": lines(r)}
        saved[f"{e['dataset']}:{e['id']}"] = row
        was = before.get(f"{e['dataset']}:{e['id']}")
        moved = f" (was {was['rank']:>3}, {was['value']:.2f})" if was else ""
        shown = "  ".join(f"{k} {v}" for k, v in row["lines"].items())
        print(f"{rank:>4}{moved}  {e['name']:<20} {r.position:>2}  value {row['value']:.2f} / ceiling {row['ceiling']:.2f}"
              f"  [{r.war_low:.1f}-{r.war_high:.1f}]  {shown}")
        print(f"       {e['note']}")
    if args.save:
        SAVED.mkdir(exist_ok=True)
        (SAVED / f"{args.save}.json").write_text(json.dumps(saved, indent=1) + "\n")
        print(f"\nsaved draft_watch/{args.save}.json")


if __name__ == "__main__":
    main()
