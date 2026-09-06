"""Unit coverage for web/org_rankings.py - the per-org rollup shared by the
System Rankings page and print_org_summaries.py."""
from web.org_rankings import ORG_POINTS_MODEL, summarize_orgs


def _row(org_id, org, rank, model_score, **extra):
    return {
        "org_id": org_id,
        "org": org,
        "rank": rank,
        "model_score": model_score,
        **extra,
    }


def test_curve_breakpoints_are_frozen():
    # These were tuned by hand against the model_score scale; a silent change
    # would reshuffle every org's score.
    assert ORG_POINTS_MODEL.ranks == [
        0, 58, 62, 65, 68, 70, 72, 75, 80, 85, 90, 100, 110, 120
    ]
    assert ORG_POINTS_MODEL.vals == [
        0, 0, 2.2, 6, 9, 11, 14, 19, 32, 45, 61, 81, 92, 100
    ]


def test_cli_shares_the_same_curve():
    import print_org_summaries

    assert print_org_summaries.player_ranking_points_model is ORG_POINTS_MODEL


def test_summarize_orgs_sorts_and_counts_tiers():
    rows = [
        _row("A", "Sea Dogs", 1, 95.0),
        _row("A", "Sea Dogs", 8, 78.0),
        _row("A", "Sea Dogs", 60, 63.0),
        _row("A", "Sea Dogs", 300, 55.0),  # below the 58 floor -> 0 points
        _row("B", "Rainiers", 40, 71.0),
        _row("B", "Rainiers", 120, 64.0),
    ]

    out = summarize_orgs(rows)

    assert [o["org_id"] for o in out] == ["A", "B"]  # A's elite bat wins
    a = out[0]
    assert a["org_name"] == "Sea Dogs"
    assert a["prospect_count"] == 4
    assert a["top10"] == 2
    assert a["top50"] == 2
    assert a["top100"] == 3
    assert a["top250"] == 3
    assert a["top500"] == 4
    assert a["org_score"] > out[1]["org_score"] > 0

    b = out[1]
    assert b["top10"] == 0
    assert b["top50"] == 1
    assert b["top100"] == 1
    assert b["top250"] == 2


def test_summarize_orgs_orders_top_prospects_best_first_and_caps():
    rows = [_row("A", "Sea Dogs", i + 1, 90.0 - i) for i in range(40)]
    # feed them in shuffled order
    rows = rows[10:] + rows[:10]

    [summary] = summarize_orgs(rows, top_n=25)

    assert len(summary["top_prospects"]) == 25
    scores = [r["model_score"] for r in summary["top_prospects"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 90.0


def test_summarize_orgs_skips_unaffiliated_players():
    # "" and "0" are free agents / unaffiliated, not a farm system
    rows = [
        _row("", None, 1, 95.0),
        _row("0", "", 2, 92.0),
        _row("A", "Sea Dogs", 3, 80.0),
    ]

    out = summarize_orgs(rows)

    assert [o["org_id"] for o in out] == ["A"]
    assert out[0]["prospect_count"] == 1
