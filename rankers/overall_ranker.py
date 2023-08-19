from rankers.base_ranker import BaseRanker
from scoring.pitcher_score import PitcherScorer
from scoring.position_player_scorer import PositionPlayerScorer


class OverallRanker(BaseRanker):
    def __init__(self):
        super().__init__(
            position_player_scorer=PositionPlayerScorer("overall"),
            pitcher_scorer=PitcherScorer("overall"),
        )

    two_way_player_threshold = 2.5
