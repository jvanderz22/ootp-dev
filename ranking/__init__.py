"""Ranking engine v2 - see plans/ranking-v2-technical-plan.md."""
from ranking.profiles import PROFILES, ScoringProfile
from ranking.ranker import PIPELINES, Ranker


def get_ranker(ranking_method: str, pipeline: str = "v2") -> Ranker:
    """Engine v2 for `ranking_method`; `pipeline="legacy"` runs today's scoring
    as v2 stages instead, which matches the legacy rankers and has a ledger."""
    try:
        profile = PROFILES[ranking_method]
    except KeyError:
        raise ValueError(f"Invalid ranking method: {ranking_method!r}")
    return Ranker(profile, pipeline)


__all__ = ["PIPELINES", "PROFILES", "Ranker", "ScoringProfile", "get_ranker"]
