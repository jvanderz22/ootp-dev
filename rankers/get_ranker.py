from rankers.draft_class_ranker import DraftClassRanker
from rankers.overall_potential_ranker import OverallPotentialRanker
from rankers.overall_ranker import OverallRanker

RANKERS = {
    "draft_class": DraftClassRanker,
    "potential": OverallPotentialRanker,
    "overall": OverallRanker,
}


def get_ranker_for_method(ranking_method: str):
    try:
        return RANKERS[ranking_method]()
    except KeyError:
        raise ValueError(f"Invalid Ranker: {ranking_method!r}")


def get_ranker(ctx=None):
    if ctx is None:
        from constants import DRAFT_CLASS_NAME
        from context import DraftClassContext

        ctx = DraftClassContext(DRAFT_CLASS_NAME)
    ranking_method = ctx.load_config().get("ranking_method")
    print(f"Ranking using ranking method {ranking_method}")
    return get_ranker_for_method(ranking_method)
