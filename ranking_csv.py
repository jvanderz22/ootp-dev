"""The C+ / StatsPlus upload list for a draft class: its ranking in the saved
custom order (custom_ranking.py), players already drafted (drafted_players.py)
left out, capped at UPLOAD_LIMIT.

The web app serves it from the download route; the CLI writes it to
processed_classes/<class>/upload_ranked_players.csv for upload_drafted_players.py.
"""
import csv

import results_store
from custom_ranking import resolve_order
from draft_class_files import _ctx
from drafted_players import get_drafted_player_ids

UPLOAD_FIELDNAMES = ["id", "name", "position", "age", "model_score", "demand"]
UPLOAD_LIMIT = 500


def ranked_csv_rows(ctx=None, with_breakdown=False):
    """The class's ranking in model order, in the string form the old
    ranked_players.csv had (see `results_store.as_csv_rows`) - what the CLI
    printers read. None if the class hasn't been scored."""
    results = results_store.class_results(_ctx(ctx), with_breakdown)
    return None if results is None else results_store.as_csv_rows(results)


def build_upload_rows(ctx):
    """Rows for the C+ upload CSV: resolved (custom) order, drafted excluded,
    capped at UPLOAD_LIMIT."""
    ordered = resolve_order(ctx, ranked_csv_rows(ctx) or [])
    drafted = get_drafted_player_ids(ctx)

    rows = []
    for player in ordered:
        if player["id"] in drafted:
            continue
        rows.append({key: player[key] for key in UPLOAD_FIELDNAMES})
        if len(rows) >= UPLOAD_LIMIT:
            break
    return rows


def write_upload_file(ctx=None) -> None:
    ctx = _ctx(ctx)
    ctx.processed_dir.mkdir(parents=True, exist_ok=True)
    with open(ctx.upload_players_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=UPLOAD_FIELDNAMES)
        for row in build_upload_rows(ctx):
            writer.writerow(row)
