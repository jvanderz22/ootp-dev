from modifiers.base_modifier import BaseModifier
from modifiers.batter_distance_from_overall_modifier import (
    BatterDistanceFromOverallModifier,
)
from modifiers.pitcher_distance_from_overall_modifier import (
    PitcherDistanceFromOverallModifier,
)
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from rankers.base_ranker import BaseRanker
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.personality_modifier import PersonalityModifier


class OverallPotentialRanker(BaseRanker):
    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            BatterHandednessModifier,
            BatterInjuryModifier,
            BatterDistanceFromOverallModifier,
            PersonalityModifier,
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            PitcherInjuryModifier,
            PitcherDistanceFromOverallModifier,
            PersonalityModifier,
        ]
