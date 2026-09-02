import csv

import pytest

from ranking_csv import build_upload_rows, write_upload_file

pytestmark = pytest.mark.slow


def test_process_class_produces_ranked_and_upload(processed_class):
    ctx = processed_class
    ranked = ctx.ranked_players_file("DraftClassRanker")
    assert ranked.exists()

    with open(ranked, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 100
    assert rows[0]["overall_ranking"] == "0"
    scores = [float(r["model_score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)  # model order is descending

    assert ctx.upload_players_file.exists()
    with open(ctx.upload_players_file, newline="") as f:
        upload = list(csv.reader(f))
    assert 0 < len(upload) <= 500
    assert len(upload[0]) == 6  # id,name,position,age,model_score,demand


def test_upload_rows_follow_custom_order_and_skip_drafted(processed_class):
    from custom_ranking import save_order
    from statsplus_api import DraftPick, write_drafted_players_file

    ctx = processed_class
    with open(ctx.ranked_players_file("DraftClassRanker"), newline="") as f:
        ids = [r["id"] for r in csv.DictReader(f)]

    write_drafted_players_file(
        ctx,
        [DraftPick(id=ids[0], name="x", position="SP", round="1", pick="1", overall="1", team="T")],
    )
    save_order(ctx, [ids[3]] + ids[:3] + ids[4:], known_ids=ids)
    write_upload_file(ctx)

    rows = build_upload_rows(ctx)
    assert rows[0]["id"] == ids[3]              # custom order applied
    assert all(r["id"] != ids[0] for r in rows)  # drafted excluded
