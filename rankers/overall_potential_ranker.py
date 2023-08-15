from modifiers.base_modifier import BaseModifier
from modifiers.batter_overall_modifier import BatterOverallModifier
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.pitcher_overall_modifier import PitcherOverallModifier
from rankers.base_ranker import BaseRanker
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.personality_modifier import PersonalityModifier


class OverallPotentialRanker(BaseRanker):
    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            BatterOverallModifier,
            BatterHandednessModifier,
            BatterInjuryModifier,
            PersonalityModifier,
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            PitcherOverallModifier,
            PitcherInjuryModifier,
            PersonalityModifier,
        ]
