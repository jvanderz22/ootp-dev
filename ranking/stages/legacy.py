"""Today's scoring as v2 stages: the legacy scorers and modifiers, run with the
same arithmetic as `rankers/base_ranker.py` so v2 reproduces legacy exactly,
with a ledger recorded alongside. Each later layer replaces one of these."""
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
    """The legacy attribute-model scorers, one batched call per side.

    `batting`, `fielding`, `running` and `pitching`, if given, are fitted
    talent models (ranking.stages.talent) that score whoever they can; the
    legacy models only run for the rest."""

    name = "legacy-model"

    def __init__(self, profile, batting=None, pitching=None, fielding=None, running=None):
        self.position_player_scorer = get_position_player_scorer(profile.ratings)
        self.pitcher_scorer = get_pitcher_scorer(profile.ratings, profile.rp_multiplier)
        self.batting = batting
        self.pitching = pitching
        self.fielding = fielding
        self.running = running

    @property
    def artifacts(self) -> dict:
        models = (self.batting, self.fielding, self.running, self.pitching)
        return {m.name: m.artifact for m in models if m}

    def run(self, states, profile):
        players = [s.player for s in states]
        none = [None] * len(players)
        fitted_bat = self.batting.score(players) if self.batting else none
        fitted_field = self.fielding.score(players) if self.fielding else none
        fitted_run = self.running.score(players) if self.running else none
        fitted_pit = self.pitching.score(players) if self.pitching else none
        batting = self.position_player_scorer.score_many(
            players,
            batting_scores=[f and f.points for f in fitted_bat],
            fielding=[f and (f.points, f.utility, f.best_position) for f in fitted_field],
            running_scores=[f and f.points for f in fitted_run],
        )
        pitching = self._pitching_scores(players, fitted_pit)
        rows = zip(states, batting, fitted_bat, fitted_field, fitted_run, pitching, fitted_pit)
        for state, bat, fit_bat, fit_field, fit_run, pit, fit_pit in rows:
            state.fitted = {"batting": fit_bat, "fielding": fit_field, "running": fit_run, "pitching": fit_pit}
            self._batting(state, bat, fit_bat and fit_bat.label, fit_field, fit_run)
            self._pitching(state, pit, fit_pit)
            if fit_bat:
                state.wrc_plus = fit_bat.wrc_plus

    def _pitching_scores(self, players, fitted):
        """[score, starter, reliever] per player: fitted where there is one, the
        legacy scorer for the rest."""
        rest = [i for i, f in enumerate(fitted) if f is None]
        legacy = iter(self.pitcher_scorer.score_many([players[i] for i in rest]) if rest else [])
        out = []
        for player, fit in zip(players, fitted):
            if fit is None:
                out.append(next(legacy))
                continue
            for role, talent, score in (("starter", fit.starter_talent, fit.starter),
                                        ("reliever", fit.reliever_talent, fit.reliever)):
                write_runtime_component(player.id, f"pitching.{role}.model", talent)
                write_runtime_component(player.id, f"pitching.{role}.base_modifier",
                                        score / talent if talent else 0.0)
                write_runtime_component(player.id, f"pitching.{role}.score", score)
            out.append([max(fit.starter, fit.reliever, 0.0), fit.starter, fit.reliever])
        return out

    @staticmethod
    def _batting(state, result, fitted_label=None, fielding=None, running=None):
        overall, batting, field, run, best_position = result
        side = state.batting
        side.model_score = overall
        side.components = {"batting": batting, "fielding": field, "running": run}
        side.best_position = best_position
        for component, weight in BATTING_WEIGHTS:
            value = side.components[component] * weight
            if component == "batting" and fitted_label:
                state.ledger.add(MODEL, f"{fitted_label} x{weight}", value, BATTING)
            elif component == "fielding" and fielding:
                state.ledger.add(MODEL, f"fielding talent ({fielding.best_position}, {fielding.runs:+.0f}"
                                 f" runs, {fielding.value:+.0f} with position) x{weight}",
                                 fielding.points * weight, BATTING)
                state.ledger.add(MODEL, f"utility x{weight}", fielding.utility * weight, BATTING)
            elif component == "running" and running:
                state.ledger.add(MODEL, f"baserunning talent ({running.runs:+.1f} runs) x{weight}", value, BATTING)
            else:
                state.ledger.add(MODEL, batting_label(component, weight), value, BATTING)

    @staticmethod
    def _pitching(state, result, fitted=None):
        score, starter, reliever = result
        side = state.pitching
        side.model_score = score
        side.components = {"starter": starter, "reliever": reliever}
        # the scorer takes the better role, floored at 0
        role, chosen = ("starter", starter) if starter > reliever else ("reliever", reliever)
        label = "SP" if role == "starter" else "RP"
        recorded = (get_runtime_components(state.player.id) or {}).get(PITCHING, {})
        model = recorded.get(role, {}).get("model", 0.0)
        if fitted:
            index = fitted.sp_index if role == "starter" else fitted.rp_index
            stuff = fitted.sp_stuff if role == "starter" else fitted.rp_stuff
            state.era = fitted.sp_era if role == "starter" else fitted.rp_era
            state.ledger.add(MODEL, f"{label} talent (Stuff {stuff:.0f} as {label}, runs allowed {index:.0f})",
                             model, PITCHING)
            state.ledger.add(MODEL, f"{label} role (stamina, pitches)", chosen - model, PITCHING)
        else:
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
