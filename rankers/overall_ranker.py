from modifiers.base_modifier import BaseModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from rankers.base_ranker import BaseRanker
from scoring.model_cache import get_pitcher_scorer, get_position_player_scorer
from modifiers.pitcher_velocity_modifier import PitcherVelocityModifier


class OverallRanker(BaseRanker):
    def __init__(self):
        super().__init__(
            position_player_scorer=get_position_player_scorer("overall"),
            pitcher_scorer=get_pitcher_scorer("overall"),
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
