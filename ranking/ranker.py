"""Engine v2: one Ranker, driven by a ScoringProfile (see
plans/ranking-v2-technical-plan.md).

Players flow through the batch stages in chunks of `batch_size` (only that many
GamePlayers are ever resident), become `RankedResult`s, and once the whole pool
is in, the pool stages (demand) run on the pre-demand order.
"""
import gc

from models.player_type import classify, prune_breakdown
from ranking.manifest import build_manifest
from ranking.results import RankedResult
from ranking.stages.demand import Demand
from ranking.stages.legacy import LegacyModel, LegacyModifiers, TwoWay
from ranking.stages.talent import Talent
from ranking.stages.value import Value
from ranking.value import DISPLAY_OFFSET
from ranking.state import PlayerState
from rankers.base_ranker import DEFAULT_BATCH_SIZE
from scoring.runtime_components import runtime_components_scope

ENGINE = "v2"
# v2 values players in WAR and shows 50 + 10 x WAR (ranking/value.py)
UNIT = {"v2": "WAR points (50 + 10 x WAR)", "legacy": "points"}


def legacy_pipeline(profile, league=None):
    """Today's scoring as stages: (batch stages, pool stages)."""
    return [LegacyModel(profile), LegacyModifiers(), TwoWay()], [Demand()]


# Engine v2's pipeline: the fitted talent models, then WAR (with the modifiers
# and the two sides combined), then demand. `legacy` keeps reproducing the
# legacy rankers (with a ledger) for comparison.
def v2_pipeline(profile, league=None):
    return [Talent(profile), Value(profile, league=league)], [Demand(offset=DISPLAY_OFFSET)]


PIPELINES = {"v2": v2_pipeline, "legacy": legacy_pipeline}


class Ranker:
    def __init__(self, profile, pipeline="v2", league=None):
        self.profile = profile
        self.pipeline = pipeline
        # the league scored (its replacement levels, ranking/value.py)
        self.league = league
        self.batch_stages, self.pool_stages = PIPELINES[pipeline](profile, league)

    def manifest(self, source_version=None) -> dict:
        artifacts = {}
        for stage in self.batch_stages + self.pool_stages:
            artifacts.update(getattr(stage, "artifacts", {}))
        return build_manifest(ENGINE, self.pipeline, self.profile, UNIT[self.pipeline], source_version, artifacts)

    def rank(self, players, batch_size: int = DEFAULT_BATCH_SIZE, progress=None) -> list:
        """Score `players` (any iterable of GamePlayer) and return RankedResults
        best-first. `progress`, if given, is called with the running count."""
        with runtime_components_scope() as store:
            # Same reasoning as the legacy ranker: nothing allocated here is
            # cyclic, and the collector walking the growing result list on every
            # pass makes a whole-league run superlinear.
            gc_was_enabled = gc.isenabled()
            gc.disable()
            try:
                results, batch, done = [], [], 0
                for player in players:
                    batch.append(player)
                    if len(batch) >= batch_size:
                        done += len(batch)
                        results.extend(self._run_batch(batch, store))
                        print(f"Evaluated {done} players")
                        if progress:
                            progress(done)
                        batch = []
                if batch:  # (legacy prints no "Evaluated" line for the last partial batch)
                    done += len(batch)
                    results.extend(self._run_batch(batch, store))
                    if progress:
                        progress(done)
                return self._finish(results)
            finally:
                if gc_was_enabled:
                    gc.enable()
                    gc.collect()

    def _run_batch(self, batch, store) -> list:
        states = [PlayerState(player) for player in batch]
        for stage in self.batch_stages:
            stage.run(states, self.profile)
        return [self._result(state, store) for state in states]

    @staticmethod
    def _result(state, store) -> RankedResult:
        player, bat, pit = state.player, state.batting, state.pitching
        return RankedResult(
            id=player.id,
            name=player.name,
            position=player.position,
            age=player.age,
            in_game_overall=player.overall,
            in_game_potential=player.potential,
            demand=player.demand,
            batting_score_component=round(bat.components["batting"], 2),
            fielding_score_component=round(bat.components["fielding"], 2),
            position_player_score=round(bat.score, 2),
            pitcher_score=round(pit.score, 2),
            starter_component=round(pit.components["starter"], 2),
            reliever_component=round(pit.components["reliever"], 2),
            running_score_component=round(bat.components["running"], 2),
            best_position=bat.best_position,
            raw_overall_score=state.value,
            breakdown=store.pop(player.id, {}) or {},
            pre_demand_score=state.value,
            ledger=state.ledger,
            wrc_plus=None if state.wrc_plus is None else round(state.wrc_plus),
            era=None if state.era is None else round(state.era, 2),
            role=state.ledger.role,
            sp_era=None if state.sp_era is None else round(state.sp_era, 2),
            rp_era=None if state.rp_era is None else round(state.rp_era, 2),
            ip=None if state.innings is None else round(state.innings),
        )

    def _finish(self, results) -> list:
        results.sort(key=lambda r: r.pre_demand_score, reverse=True)
        for i, result in enumerate(results):
            result.pre_demand_rank = i + 1
        for stage in self.pool_stages:
            stage.run(results, self.profile)
        for result in results:
            # v2's side scores are WAR, so both can be at or below replacement;
            # the listed position decides then
            position = result.position if self.pipeline == "v2" else None
            result.player_type = classify(result.position_player_score, result.pitcher_score, position)
            result.breakdown = prune_breakdown(result.breakdown, result.player_type)
        results.sort(key=lambda r: r.overall_score, reverse=True)
        for i, result in enumerate(results):
            result.rank = i + 1
        return results
