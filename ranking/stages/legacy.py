"""Legacy scoring as stages: the legacy scorers and modifiers, run with the same
arithmetic as `rankers/base_ranker.py` so the `legacy` pipeline reproduces the
legacy rankers exactly, with a ledger recorded alongside. v2 uses none of
them (plans/xgboost-phaseout-plan.md, step 3)."""
from ranking.ledger import BATTING, MODEL, MODIFIERS, PITCHING, TWO_WAY
from ranking.profiles import modifier_name
from ranking.stages.base import BatchStage
from scoring.model_cache import get_pitcher_scorer, get_position_player_scorer
from scoring.runtime_components import get_runtime_components, write_runtime_component

# PositionPlayerScorer's weighting of its three models
BATTING_WEIGHTS = (("batting", 0.73), ("fielding", 0.22), ("running", 0.05))


def batting_label(component, weight) -> str:
    return f"{component} model x{weight}"


class LegacyModel(BatchStage):
    """The legacy attribute-model scorers, one batched call per side (the
    legacy pipeline only: v2 reads the fitted talent models instead)."""

    name = "legacy-model"

    def __init__(self, profile):
        self.position_player_scorer = get_position_player_scorer(profile.ratings)
        self.pitcher_scorer = get_pitcher_scorer(profile.ratings, profile.rp_multiplier)

    def run(self, states, profile):
        players = [s.player for s in states]
        batting = self.position_player_scorer.score_many(players)
        pitching = self.pitcher_scorer.score_many(players)
        for state, bat, pit in zip(states, batting, pitching):
            self._batting(state, bat)
            self._pitching(state, pit)

    @staticmethod
    def _batting(state, result):
        overall, batting, field, run, best_position = result
        side = state.batting
        side.model_score = overall
        side.components = {"batting": batting, "fielding": field, "running": run}
        side.best_position = best_position
        for component, weight in BATTING_WEIGHTS:
            state.ledger.add(MODEL, batting_label(component, weight), side.components[component] * weight, BATTING)

    @staticmethod
    def _pitching(state, result):
        score, starter, reliever = result
        side = state.pitching
        side.model_score = score
        side.components = {"starter": starter, "reliever": reliever}
        # the scorer takes the better role, floored at 0
        role, chosen = ("starter", starter) if starter > reliever else ("reliever", reliever)
        label = "SP" if role == "starter" else "RP"
        recorded = (get_runtime_components(state.player.id) or {}).get(PITCHING, {})
        model = recorded.get(role, {}).get("model", 0.0)
        state.ledger.add(MODEL, f"{label} model", model, PITCHING)
        state.ledger.add(MODEL, f"{label} role adjustments", chosen - model, PITCHING)
        if chosen <= 0:
            state.ledger.add(MODEL, "no pitching value", -chosen, PITCHING)


class LegacyModifiers(BatchStage):
    """The profile's multiplicative modifiers. As in legacy, each is fed the
    side's unmodified model score, and the side's score is model x the product."""

    name = "legacy-modifiers"

    def run(self, states, profile):
        sides = (
            (BATTING, profile.shared_modifiers + profile.batting_modifiers),
            (PITCHING, profile.shared_modifiers + profile.pitching_modifiers),
        )
        for state in states:
            player = state.player
            for side_name, modifiers in sides:
                side = getattr(state, side_name)
                product, running = 1, side.model_score
                for modifier in modifiers:
                    factor = modifier.calculate_player_modifier(player, side.model_score)
                    name = modifier_name(modifier)
                    write_runtime_component(player.id, f"{side_name}.modifiers.{name}", factor)
                    product *= factor
                    side.modifiers.append((name, factor))
                    running = state.ledger.scale(MODIFIERS, name, running, factor, side_name)
                write_runtime_component(player.id, f"{side_name}.modifier_total", product)
                side.score = side.model_score * product


class TwoWay(BatchStage):
    """Combine the sides: the stronger one counts, plus a bonus of a share of the
    weaker one when they're close."""

    name = "two-way"

    def run(self, states, profile):
        for state in states:
            batter, pitcher = state.batting.score, state.pitching.score
            high, low = (batter, pitcher) if batter > pitcher else (pitcher, batter)
            state.ledger.side = BATTING if batter > pitcher else PITCHING
            value = high
            if (high - low) < (high / profile.two_way_threshold):
                bonus = low * profile.two_way_bonus
                state.ledger.add(TWO_WAY, "two-way bonus", bonus)
                value += bonus
            state.value = value
