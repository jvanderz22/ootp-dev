from modifiers.base_modifier import BaseModifier
from modifiers.base_rank_modifier import BaseRankModifier
from modifiers.draft_batter_overall_modifier import DraftBatterOverallModifier
from modifiers.draft_demand_modifier import DraftDemandModifier
from modifiers.draft_rank_personality_modifier import DraftRankPersonalityModifier
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.draft_pitcher_overall_modifier import DraftPitcherOverallModifier
from modifiers.scouting_accuracy_modifier import ScoutingAccuracyModifier
from rankers.base_ranker import BaseRanker
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.draft_age_modifier import DraftAgeModifier
from modifiers.personality_modifier import PersonalityModifier


class DraftClassRanker(BaseRanker):
    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return [
            DraftBatterOverallModifier,
            BatterHandednessModifier,
            BatterInjuryModifier,
            ScoutingAccuracyModifier,
            PersonalityModifier,
            DraftAgeModifier,
        ]

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return [
            DraftPitcherOverallModifier,
            PitcherInjuryModifier,
            PersonalityModifier,
            ScoutingAccuracyModifier,
            DraftAgeModifier,
        ]

    @property
    def rank_adjusted_modifiers(self) -> list[BaseRankModifier]:
        return [DraftDemandModifier, DraftRankPersonalityModifier]

    def aggregate_pitcher_batter_scores(self, batter_score, pitcher_score):
        high_score = batter_score if batter_score > pitcher_score else pitcher_score
        low_score = batter_score if batter_score < pitcher_score else pitcher_score
        total_score = high_score
        # Add a bonus for potential two way players
        if (high_score - low_score) < (high_score / 2.2):
            total_score += low_score * 0.15
        return total_score
