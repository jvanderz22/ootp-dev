"""Build a scratch DATA_DIR holding one draft class, processed under every
ranking engine - enough for the web app to show a class table and player cards.

    activate/bin/python .claude/skills/run-ootp-dev/seed.py DATA_DIR [--csv PATH] [--name NAME]

Without --csv the class is the synthetic one the e2e tests use (80 players,
seeded, no real data needed). With --csv it is a real OOTP export, e.g.
fly_data/datasets/yfmlb-2042-draft.csv. Run from the repo root.
"""
import argparse
import contextlib
import io
import os
import shutil
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("data_dir")
parser.add_argument("--csv", help="a dataset CSV (default: the synthetic e2e class)")
parser.add_argument("--name", help="class name (default: the CSV's stem, or smoke-class)")
args = parser.parse_args()

data_dir = Path(args.data_dir).resolve()
name = args.name or (Path(args.csv).stem if args.csv else "smoke-class")
if data_dir.exists():
    shutil.rmtree(data_dir)
(data_dir / "datasets").mkdir(parents=True)
(data_dir / "processed_classes" / name).mkdir(parents=True)

# DATA_DIR has to be set before anything that opens app.db is imported
os.environ["DATA_DIR"] = str(data_dir)
sys.path.insert(0, os.getcwd())

if args.csv:
    shutil.copy(args.csv, data_dir / "datasets" / f"{name}.csv")
else:
    from tests.e2e_fixtures import make_draft_class_csv

    (data_dir / "datasets" / f"{name}.csv").write_text(make_draft_class_csv(n=80, seed=11))

import ranking_engine
import results_store
from context import DraftClassContext
from pipeline import process_class

ctx = DraftClassContext(name)
ctx.register("draft_class")
with contextlib.redirect_stdout(io.StringIO()):  # the pipeline prints per-player progress
    process_class(ctx)
counts = {e: results_store.run_info("class", name, "draft_class", e)["player_count"] for e in ranking_engine.ENGINES}
print(f"{name}: {counts} -> {data_dir}")
