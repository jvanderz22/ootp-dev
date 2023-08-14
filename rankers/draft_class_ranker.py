from models.game_players import GamePlayer
from models.player_score import PlayerScore
from modifiers.batter_overall_modifier import BatterOverallModifier
from modifiers.draft_demand_modifier import DraftDemandModifier
from modifiers.draft_rank_personality_modifier import DraftRankPersonalityModifier
from modifiers.pitcher_injury_modifier import PitcherInjuryModifier
from modifiers.pitcher_overall_modifier import PitcherOverallModifier
from scoring.position_player_score import (
    calculate_position_player_score,
)
from scoring.pitcher_score import calculate_pitcher_score
from modifiers.batter_injury_modifier import BatterInjuryModifier
from modifiers.batter_handedness_modifier import BatterHandednessModifier
from modifiers.draft_age_modifier import DraftAgeModifier
from modifiers.personality_modifier import PersonalityModifier


class DraftClassRanker:
    def rank(self, players: list[GamePlayer]):
        player_scores = []
        all_players = {}
        for player in players:
            all_players[player.id] = player
            [
                position_player_score,
                batting_score,
                fielding_score,
            ] = self.__calculate_position_player_score(player)
            pitcher_score = self.__calculate_pitcher_score(player)

            player_score = PlayerScore(
                id=player.id,
                batting_score_component=round(batting_score, 2),
                fielding_score_component=round(fielding_score, 2),
                position_player_score=round(position_player_score, 2),
                pitcher_score=round(pitcher_score, 2),
                raw_overall_score=self.__aggregate_pitcher_batter_scores(
                    position_player_score, pitcher_score
                ),
            )
            player_scores.append(player_score)

        sorted_player_scores = sorted(
            player_scores, key=lambda score: score.raw_overall_score, reverse=True
        )

        for i, score in enumerate(sorted_player_scores):
            player = all_players[score.id]
            overall_score = self.__calculate_rank_adjusted_score(
                player, score.raw_overall_score, i
            )
            score.overall_score = overall_score

        sorted_player_scores = sorted(
            player_scores, key=lambda score: score.overall_score, reverse=True
        )
        return sorted_player_scores

    def __calculate_position_player_score(self, player: GamePlayer):
        modifier = self.__get_position_player_modifier(player)
        [
            position_player_score,
            batting_score,
            fielding_score,
        ] = calculate_position_player_score(player)
        return [position_player_score * modifier, batting_score, fielding_score]

    def __get_position_player_modifier(self, player: GamePlayer):
        modifier = 1
        overall_modifier = BatterOverallModifier.calculate_player_modifier(
            player,
        )
        handednesss_modifier = BatterHandednessModifier.calculate_player_modifier(
            player,
        )
        injury_modifier = BatterInjuryModifier.calculate_player_modifier(player)
        personality_modifier = PersonalityModifier.calculate_player_modifier(player)
        draft_age_modifier = DraftAgeModifier.calculate_player_modifier(player)
        modifier = (
            modifier
            * overall_modifier
            * handednesss_modifier
            * injury_modifier
            * personality_modifier
            * draft_age_modifier
        )

        return modifier

    def __calculate_pitcher_score(self, player: GamePlayer):
        modifier = self.__get_pitcher_modifier(player)
        pitcher_score = calculate_pitcher_score(player)
        return pitcher_score * modifier

    def __get_pitcher_modifier(self, player: GamePlayer):
        modifier = 1
        overall_modifier = PitcherOverallModifier.calculate_player_modifier(
            player,
        )
        injury_modifier = PitcherInjuryModifier.calculate_player_modifier(player)
        personality_modifier = PersonalityModifier.calculate_player_modifier(player)
        draft_age_modifier = DraftAgeModifier.calculate_player_modifier(player)
        modifier = (
            modifier
            * overall_modifier
            * injury_modifier
            * personality_modifier
            * draft_age_modifier
        )
        return modifier

    def __calculate_rank_adjusted_score(self, player, raw_score, rank):
        demand_adjusted_score = DraftDemandModifier.calculate_modified_score(
            player, rank, raw_score
        )
        personality_adjusted_score = (
            DraftRankPersonalityModifier.calculate_modified_score(
                player, rank, demand_adjusted_score
            )
        )
        return personality_adjusted_score

    def __aggregate_pitcher_batter_scores(self, batter_score, pitcher_score):
        high_score = batter_score if batter_score > pitcher_score else pitcher_score
        low_score = batter_score if batter_score < pitcher_score else pitcher_score
        total_score = high_score
        # Add a bonus for potential two way players
        if (high_score - low_score) < (high_score / 2.2):
            total_score += low_score * 0.15
        return total_score
