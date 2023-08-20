import json
from draft_class_files import get_draft_class_config_file
from rankers.current_potential_ranker import CurrentPotentialRanker
from rankers.draft_class_ranker import DraftClassRanker
from rankers.overall_potential_ranker import OverallPotentialRanker
from rankers.overall_ranker import OverallRanker


def get_ranker():
    ranking_method = None

    with open(get_draft_class_config_file(), "r") as jsonfile:
        json_data = json.load(jsonfile)
        ranking_method = json_data.get("ranking_method")
        print(f"Ranking using ranking method {ranking_method}")
    if ranking_method == "draft_class":
        return DraftClassRanker()
    elif ranking_method == "potential":
        return OverallPotentialRanker()
    elif ranking_method == "current_potential":
        return CurrentPotentialRanker()
    elif ranking_method == "overall":
        return OverallRanker()
    raise ValueError("Invalid Ranker")
