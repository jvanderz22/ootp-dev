from modifiers.base_modifier import BaseModifier
from modifiers.batter_hit_profile_modifier import BatterHitProfileModifier
from modifiers.draft_batter_overall_modifier import DraftBatterOverallModifier
from modifiers.draft_pitcher_overall_modifier import DraftPitcherOverallModifier
from modifiers.draft_pitcher_stuff_modifier import DraftPitcherStuffModifier
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.scouting_accuracy_modifier import ScoutingAccuracyModifier
from rankers.base_ranker import BaseRanker
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.personality_modifier import PersonalityModifier
from modifiers.pitcher_velocity_modifier import PitcherVelocityModifier
from scoring.pitcher_scorer import PitcherScorer


class OverallPotentialRanker(BaseRanker):
    def __init__(self, pitcher_scorer=PitcherScorer()):
        super().__init__(pitcher_scorer=pitcher_scorer)

    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            DraftBatterOverallModifier,
            BatterHandednessModifier,
            BatterHitProfileModifier(),
            BatterInjuryModifier,
            ScoutingAccuracyModifier,
            PersonalityModifier,
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            DraftPitcherOverallModifier,
            DraftPitcherStuffModifier,
            PitcherVelocityModifier,
            PitcherInjuryModifier,
            PersonalityModifier,
            ScoutingAccuracyModifier,
        ]

    def filter_players(self, players):
        return players
