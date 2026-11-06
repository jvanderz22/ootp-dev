"""Ranking engine v2 - see plans/ranking-v2-technical-plan.md."""
from ranking.profiles import PROFILES, ScoringProfile
from ranking.ranker import Ranker


def get_ranker(ranking_method: str) -> Ranker:
    try:
        return Ranker(PROFILES[ranking_method])
    except KeyError:
        raise ValueError(f"Invalid ranking method: {ranking_method!r}")


__all__ = ["PROFILES", "Ranker", "ScoringProfile", "get_ranker"]
