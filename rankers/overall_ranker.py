from modifiers.base_modifier import BaseModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from rankers.base_ranker import BaseRanker
from scoring.pitcher_scorer import PitcherScorer
from scoring.position_player_scorer import PositionPlayerScorer
from modifiers.pitcher_velocity_modifier import PitcherVelocityModifier


class OverallRanker(BaseRanker):
    def __init__(self):
        super().__init__(
            position_player_scorer=PositionPlayerScorer("overall"),
            pitcher_scorer=PitcherScorer("overall"),
        )

    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            BatterHandednessModifier,
            BatterHitProfileModifier(True),
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            PitcherVelocityModifier,
        ]

    two_way_player_threshold = 2.5
