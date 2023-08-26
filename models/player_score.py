from dataclasses import dataclass


@dataclass
class PlayerScore:
    id: int
    batting_score_component: float
    fielding_score_component: float
    position_player_score: float
    pitcher_score: float
    starter_component: float
    reliever_component: float
    raw_overall_score: float
    overall_score: float = None
