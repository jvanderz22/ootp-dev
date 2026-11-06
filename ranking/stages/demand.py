"""The demand step: the profile's rank-adjusted modifiers (signability), run
last on the pre-demand order - legacy `_apply_rank_adjustment`, unchanged."""
from ranking.ledger import DEMAND
from ranking.profiles import modifier_name
from ranking.stages.base import PoolStage
from scoring.runtime_components import set_path


class Demand(PoolStage):
    name = "demand"

    def run(self, results, profile):
        # `results` arrive in pre-demand order with `pre_demand_rank` set
        for result in results:
            score = result.pre_demand_score
            for modifier in profile.demand_modifiers:
                factor = modifier.calculate_modified_score(result, result.pre_demand_rank)
                if float(factor) != 1.0:
                    set_path(
                        result.breakdown,
                        f"rank_adjust.modifiers.{modifier_name(modifier)}",
                        round(float(factor), 2),
                    )
                score = result.ledger.scale(DEMAND, modifier_name(modifier), score, factor)
            set_path(result.breakdown, "rank_adjust.pre_rank", result.pre_demand_rank)
            set_path(result.breakdown, "rank_adjust.pre_score", round(float(result.pre_demand_score), 2))
            result.overall_score = score
