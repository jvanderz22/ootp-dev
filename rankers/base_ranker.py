from abc import ABC
import inspect
import json
from models.game_players import GamePlayer
from models.player_score import PlayerScore
from modifiers.base_modifier import BaseModifier
from modifiers.base_rank_modifier import BaseRankModifier
from scoring.position_player_scorer import (
    PositionPlayerScorer,
)
from scoring.pitcher_scorer import PitcherScorer
from scoring.runtime_components import get_runtime_components, write_runtime_component


class BaseRanker(ABC):
    def __init__(
        self,
        position_player_scorer=PositionPlayerScorer(),
        pitcher_scorer=PitcherScorer(),
    ):
        self.position_player_scorer = position_player_scorer
        self.pitcher_scorer = pitcher_scorer

    two_way_player_threshold = 1.8

    @property
    def shared_modifiers(self) -> list[BaseModifier]:
        return []

    @property
    def position_player_modifiers(self) -> list[BaseModifier]:
        return []

    @property
    def pitcher_modifiers(self) -> list[BaseModifier]:
        return []

    @property
    def rank_adjusted_modifiers(self) -> list[BaseRankModifier]:
        return []

    def filter_players(self, players):
        return players

    def rank(self, players: list[GamePlayer]):
        player_scores = []
        all_players = {}
        players = self.filter_players(players)
        log = len(players) > 3000
        for i, player in enumerate(players):
            if log and i % 500 == 0 and i > 0:
                print(f"Evaluated {i} players of {len(players)}")
            all_players[player.id] = player
            [
                position_player_score,
                batting_score,
                fielding_score,
            ] = self.calculate_position_player_score(player)
            [
                pitcher_score,
                starter_score,
                reliever_score,
            ] = self.calculate_pitcher_score(player)

            player_score = PlayerScore(
                id=player.id,
                batting_score_component=round(batting_score, 2),
                fielding_score_component=round(fielding_score, 2),
                position_player_score=round(position_player_score, 2),
                pitcher_score=round(pitcher_score, 2),
                starter_component=round(starter_score, 2),
                reliever_component=round(reliever_score, 2),
                raw_overall_score=self.aggregate_pitcher_batter_scores(
                    position_player_score, pitcher_score
                ),
            )
            player_scores.append(player_score)

        sorted_player_scores = sorted(
            player_scores, key=lambda score: score.raw_overall_score, reverse=True
        )

        for i, score in enumerate(sorted_player_scores):
            player = all_players[score.id]
            overall_score = self.calculate_rank_adjusted_score(
                player, score.raw_overall_score, i + 1
            )
            score.overall_score = overall_score
            score.components = json.loads(
                json.dumps(str(get_runtime_components(player.id)))
            )

        sorted_player_scores = sorted(
            player_scores, key=lambda score: score.overall_score, reverse=True
        )
        return sorted_player_scores

    def calculate_position_player_score(self, player: GamePlayer) -> float:
        [
            position_player_score,
            batting_score,
            fielding_score,
        ] = self.position_player_scorer.score(player)
        modifier = self.get_position_player_modifier(player, position_player_score)
        return [position_player_score * modifier, batting_score, fielding_score]

    def get_position_player_modifier(self, player: GamePlayer, model_score: float) -> float:
        modifier_val = 1
        for modifier in self.shared_modifiers + self.position_player_modifiers:
            mod_val = modifier.calculate_player_modifier(player, model_score)
            modifier_name = (
                modifier.__name__
                if inspect.isclass(modifier)
                else modifier.__class__.__name__
            )

            write_runtime_component(player.id, f"Pos Modifier {modifier_name}", mod_val)
            modifier_val *= mod_val

        write_runtime_component(player.id, f"Total Pos Modifier", modifier_val)
        return modifier_val

    def calculate_pitcher_score(self, player: GamePlayer) -> float:
        [
            pitcher_score,
            starter_component,
            reliever_component,
        ] = self.pitcher_scorer.score(player)
        modifier = self.get_pitcher_modifier(player, pitcher_score)
        return [pitcher_score * modifier, starter_component, reliever_component]

    def get_pitcher_modifier(self, player: GamePlayer, model_score: float) -> float:
        modifier_val = 1
        for modifier in self.shared_modifiers + self.pitcher_modifiers:
            mod_val = modifier.calculate_player_modifier(player, model_score)
            write_runtime_component(
                player.id, f"Pitcher Modifier {modifier.__name__}", mod_val
            )
            modifier_val *= mod_val
        write_runtime_component(player.id, f"Total Pitcher Modifier", modifier_val)
        return modifier_val

    def calculate_rank_adjusted_score(self, player, raw_score, rank) -> float:
        score = raw_score
        for modifier in self.rank_adjusted_modifiers:
            mod_val = modifier.calculate_modified_score(player, rank)
            if float(mod_val) != float(1):
                write_runtime_component(
                    player.id, f"Rank-adj Modifier {modifier.__name__}", mod_val
                )
            score *= mod_val

        write_runtime_component(player.id, f"Pre Rank-adj Rank", rank)
        write_runtime_component(player.id, f"Pre Rank-adj Score", raw_score)
        return score

    def aggregate_pitcher_batter_scores(self, batter_score, pitcher_score) -> float:
        high_score = batter_score if batter_score > pitcher_score else pitcher_score
        low_score = batter_score if batter_score < pitcher_score else pitcher_score
        total_score = high_score
        # Add a bonus for potential two way players
        if (high_score - low_score) < (high_score / self.two_way_player_threshold):
            total_score += low_score * 0.15
        return total_score
