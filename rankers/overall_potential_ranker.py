from modifiers.base_modifier import BaseModifier
from modifiers.batter_distance_from_overall_modifier import (
    BatterDistanceFromOverallModifier,
)
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from modifiers.pitcher_distance_from_overall_modifier import (
    PitcherDistanceFromOverallModifier,
)
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.scouting_accuracy_modifier import ScoutingAccuracyModifier
from rankers.base_ranker import BaseRanker
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.personality_modifier import PersonalityModifier
from scoring.pitcher_scorer import PitcherScorer, PITCHER_EXPONENT, PITCHER_MULTIPLIER


class OverallPotentialRanker(BaseRanker):
    def __init__(self, pitcher_scorer=PitcherScorer()):
        super().__init__(pitcher_scorer=pitcher_scorer)

    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            BatterHandednessModifier,
            BatterInjuryModifier,
            BatterHitProfileModifier(),
            BatterDistanceFromOverallModifier,
            ScoutingAccuracyModifier,
            PersonalityModifier,
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            PitcherInjuryModifier,
            PitcherDistanceFromOverallModifier,
            ScoutingAccuracyModifier,
            PersonalityModifier,
        ]

    def filter_players(self, players):
        return [player for player in players if player.age <= 27]
