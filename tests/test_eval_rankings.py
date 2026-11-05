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
