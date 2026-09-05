from abc import ABC
import inspect
from models.game_players import GamePlayer
from models.scored_player import ScoredPlayer
from modifiers.base_modifier import BaseModifier
from modifiers.base_rank_modifier import BaseRankModifier
from scoring.position_player_scorer import (
    PositionPlayerScorer,
)
from scoring.pitcher_scorer import PitcherScorer
from scoring.runtime_components import (
    runtime_components_scope,
    write_runtime_component,
)

# A draft class fits comfortably in one batch; a whole-league snapshot (~15k
# players) does not - scoring it all at once holds every GamePlayer, every
# runtime-component dict and the models in memory simultaneously, which is what
# was OOM-killing the 512MB box. Batching keeps only this many players resident
# at a time; the lightweight ScoredPlayer results accumulate for the final sort.
DEFAULT_BATCH_SIZE = 1500


class BaseRanker(ABC):
    def __init__(
        self,
        position_player_scorer=None,
        pitcher_scorer=None,
    ):
        from scoring.model_cache import get_pitcher_scorer, get_position_player_scorer

        self.position_player_scorer = (
            position_player_scorer or get_position_player_scorer()
        )
        self.pitcher_scorer = pitcher_scorer or get_pitcher_scorer()

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

    def rank(self, players, batch_size: int = DEFAULT_BATCH_SIZE):
        """Score `players` (a list or any iterable of GamePlayer) and return a
        list of ScoredPlayer sorted best-first, ranks applied.

        Players are consumed in chunks of `batch_size` so the whole pool is never
        resident at once; only the lightweight results accumulate. Pass a
        `batch_size` >= the player count (or a class-sized default) to score in a
        single pass - behaviour is identical either way for rankers without
        rank-adjusted modifiers, and rank-adjusted modifiers still see the global
        rank because they run after every batch is scored.
        """
        with runtime_components_scope() as store:
            return self._rank_impl(players, batch_size, store)

    def _rank_impl(self, players, batch_size, store):
        results = []
        batch = []
        done = 0
        for player in players:
            batch.append(player)
            if len(batch) >= batch_size:
                done += len(batch)
                self._score_batch(batch, store, results)
                print(f"Evaluated {done} players")
                batch = []
        if batch:
            self._score_batch(batch, store, results)

        results.sort(key=lambda r: r.raw_overall_score, reverse=True)
        for i, result in enumerate(results):
            result.overall_score = self._apply_rank_adjustment(result, i + 1)
            result.components = str(result.components)
        results.sort(key=lambda r: r.overall_score, reverse=True)
        return results

    def _score_batch(self, batch, store, results):
        """Score one chunk of GamePlayers, appending a ScoredPlayer for each and
        draining that player's runtime-component dict out of the shared store so
        it doesn't pile up across batches."""
        for player in self.filter_players(batch):
            (
                position_player_score,
                batting_score,
                fielding_score,
                running_score,
            ) = self.calculate_position_player_score(player)
            (
                pitcher_score,
                starter_score,
                reliever_score,
            ) = self.calculate_pitcher_score(player)
            results.append(
                ScoredPlayer(
                    id=player.id,
                    name=player.name,
                    position=player.position,
                    age=player.age,
                    in_game_overall=player.overall,
                    in_game_potential=player.potential,
                    demand=player.demand,
                    batting_score_component=round(batting_score, 2),
                    fielding_score_component=round(fielding_score, 2),
                    position_player_score=round(position_player_score, 2),
                    pitcher_score=round(pitcher_score, 2),
                    starter_component=round(starter_score, 2),
                    reliever_component=round(reliever_score, 2),
                    running_score_component=round(running_score, 2),
                    raw_overall_score=self.aggregate_pitcher_batter_scores(
                        position_player_score, pitcher_score
                    ),
                    components=store.pop(player.id, {}) or {},
                )
            )

    def _apply_rank_adjustment(self, result: ScoredPlayer, rank: int) -> float:
        """Port of `calculate_rank_adjusted_score` for the batched path: the
        player's GamePlayer is long gone, so read what the rank modifiers need
        off the ScoredPlayer and fold the debug values straight into its
        `components` dict (same keys/rounding `write_runtime_component` would use).
        """
        score = result.raw_overall_score
        for modifier in self.rank_adjusted_modifiers:
            mod_val = modifier.calculate_modified_score(result, rank)
            if float(mod_val) != 1.0:
                result.components[f"Rank-adj Modifier {modifier.__name__}"] = round(
                    float(mod_val), 2
                )
            score *= mod_val
        result.components["Pre Rank-adj Rank"] = rank
        if result.raw_overall_score > 0:
            result.components["Pre Rank-adj Score"] = round(
                float(result.raw_overall_score), 2
            )
        return score

    def calculate_position_player_score(self, player: GamePlayer) -> float:
        [
            position_player_score,
            batting_score,
            fielding_score,
            running_score,
        ] = self.position_player_scorer.score(player)
        modifier = self.get_position_player_modifier(player, position_player_score)
        return [
            position_player_score * modifier,
            batting_score,
            fielding_score,
            running_score,
        ]

    def get_position_player_modifier(
        self, player: GamePlayer, model_score: float
    ) -> float:
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
