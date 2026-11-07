"""The outcome and metric helpers behind eval_rankings.py."""
import pytest

import eval_rankings
from eval_rankings import BUST, draft_outcome, top_k_mean, within_bucket_rho


@pytest.mark.parametrize(
    "row, expected",
    [
        (None, BUST),                                    # gone from the league
        ({"Age": "25", "OVR": "45", "POT": "50"}, 45),   # arrived: judged on OVR
        ({"Age": "24", "OVR": "45", "POT": "50"}, 50),   # still developing: POT now
        ({"Age": "", "OVR": "45", "POT": "50"}, 50),     # unknown age: POT now
    ],
)
def test_draft_outcome(row, expected):
    assert draft_outcome(row) == expected


def test_top_k_mean_splits_ties_at_the_cutoff():
    # top 2 by key: the 70 (outcome 50), then one of the two tied 60s
    # (outcomes 40 / 30) counted as their mean, 35
    assert top_k_mean([70, 60, 60, 50], [50, 40, 30, 99], 2) == pytest.approx((50 + 35) / 2)


def test_within_bucket_rho_weights_by_size_and_skips_small_buckets(monkeypatch):
    monkeypatch.setattr(eval_rankings, "MIN_BUCKET", 3)
    keys = [1, 2, 3, 4, 1, 2, 3, 9]
    outcomes = [1, 2, 3, 4, 3, 2, 1, 0]
    buckets = ["a", "a", "a", "a", "b", "b", "b", "c"]   # "c" has 1 player
    # a: perfectly ordered (+1, 4 players); b: perfectly reversed (-1, 3 players)
    assert within_bucket_rho(keys, outcomes, buckets) == pytest.approx((4 - 3) / 7)


# ------------------------------------------------------------------ parity / explain
def _class():
    import csv
    import io

    from tests.e2e_fixtures import make_draft_class_csv

    rows = list(csv.DictReader(io.StringIO(make_draft_class_csv(n=60, seed=7))))
    return {"yfmlb-2040-draft": rows}


def _ranked(engine, classes):
    return eval_rankings.results(engine, ["draft"], [], classes)


def test_pool_parity_is_clean_for_matching_engines():
    classes = _class()
    head, base = _ranked("v2", classes), _ranked("legacy", classes)
    m = eval_rankings.pool_parity(head["draft"]["yfmlb-2040-draft"], base["draft"]["yfmlb-2040-draft"])
    assert m["n"] == 60 and m["rows"] == 0 and m["order_from"] is None and not m["fields"]


def test_pool_parity_finds_fields_breakdown_leaves_and_order():
    from dataclasses import replace

    base = _ranked("legacy", _class())["draft"]["yfmlb-2040-draft"]
    head = [replace(r, breakdown=dict(r.breakdown)) for r in base]
    head[0], head[1] = head[1], head[0]
    head[1] = replace(head[1], overall_score=head[1].overall_score + 1)
    head[1].breakdown["rank_adjust"] = {**head[1].breakdown.get("rank_adjust", {}), "pre_rank": -1}
    m = eval_rankings.pool_parity(head, base)
    assert m["rows"] == 1
    assert m["fields"]["overall_score"][0] == 1
    assert m["fields"]["breakdown.rank_adjust.pre_rank"][0] == 1
    assert m["order_from"] == 1 and m["ranks_moved"] == 2


def test_explain_shows_both_engines_ledgers(capsys):
    classes = _class()
    head, base = _ranked("v2", classes), _ranked("legacy", classes)
    target = head["draft"]["yfmlb-2040-draft"][0]
    eval_rankings.print_explain([target.id], head, "v2", base, "legacy", [], classes)
    out = capsys.readouterr().out
    assert f"ID {target.id}" in out
    assert "legacy" in out and "v2" in out
    assert "the legacy-pipeline ledger gives" not in out  # it reproduces legacy
    score_line = next(line for line in out.splitlines() if line.strip().startswith("score"))
    assert score_line.split()[1:] == [f"{target.overall_score:.2f}"] * 2
    assert "change" in out


def test_explain_matches_by_name_case_insensitively(capsys):
    classes = _class()
    head = _ranked("v2", classes)
    target = head["draft"]["yfmlb-2040-draft"][5]
    eval_rankings.print_explain([target.name.upper()], head, "v2", None, None, [], classes)
    assert f"ID {target.id}" in capsys.readouterr().out
