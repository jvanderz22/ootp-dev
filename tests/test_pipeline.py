import csv

import pytest

import results_store
from ranking_csv import build_upload_rows, ranked_csv_rows, write_upload_file

pytestmark = pytest.mark.slow


def test_process_class_stores_the_ranking(processed_class):
    ctx = processed_class
    run = results_store.run_info(results_store.CLASS, ctx.name, "draft_class")
    assert run["source_version"] == ctx.data_version

    rows = ranked_csv_rows(ctx)
    assert len(rows) == run["player_count"] > 100
    assert rows[0]["overall_ranking"] == "0"
    scores = [float(r["model_score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)  # model order is descending

    # every breakdown is pruned to the player's type
    for r in results_store.class_results(ctx, with_breakdown=True):
        dropped = {"Hitter": "pitching", "Pitcher": "batting"}.get(r["player_type"])
        assert dropped not in r["breakdown"]
        assert "rank_adjust" in r["breakdown"]

    write_upload_file(ctx)
    with open(ctx.upload_players_file, newline="") as f:
        upload = list(csv.reader(f))
    assert 0 < len(upload) <= 500
    assert len(upload[0]) == 6  # id,name,position,age,model_score,demand


def test_upload_rows_follow_custom_order_and_skip_drafted(processed_class):
    from custom_ranking import save_order
    from drafted_players import save_picks
    from statsplus_api import DraftPick

    ctx = processed_class
    ids = [r["id"] for r in ranked_csv_rows(ctx)]

    save_picks(
        ctx,
        [DraftPick(id=ids[0], name="x", position="SP", round="1", pick="1", overall="1", team="T")],
    )
    save_order(ctx, [ids[3]] + ids[:3] + ids[4:], known_ids=ids)
    write_upload_file(ctx)

    rows = build_upload_rows(ctx)
    assert rows[0]["id"] == ids[3]              # custom order applied
    assert all(r["id"] != ids[0] for r in rows)  # drafted excluded
