"""CLI entry point: process the class named in constants.py.

The real work lives in pipeline.process_class(ctx); this shim keeps the old
command (`python3 run.py`) and its distribution printout working.
"""
from constants import DRAFT_CLASS_NAME
from context import DraftClassContext
from pipeline import process_class
from print_pos_distribution import print_top_distribution

if __name__ == "__main__":
    ctx = DraftClassContext(DRAFT_CLASS_NAME)
    print(f"Running evals for {DRAFT_CLASS_NAME}!")
    process_class(ctx)

    for count in (10, 20, 50, 100, 400, 1000):
        print_top_distribution(count)
        print("\n\n\n")
