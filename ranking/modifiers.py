"""The legacy modifiers v2 keeps, weighted by WAR instead of legacy points.

Two of them weight themselves by how good the side is, through a
RankGradiatedModel on the legacy score: AgeModifier (age counts fully for a
weak prospect, half at 55 points, not at all from 130) and
DraftSecondaryPersonalityModifier (personality and leadership count less for
a better player). v2 feeds them the side's WAR before its modifiers instead.
Their thresholds were converted once (2026-11-09; plans/xgboost-phaseout-plan.md,
step 3) from legacy points to that WAR, and frozen: the WAR v2's sides had at
each threshold when the points bridges still fed them (daca855; an isotonic
fit over the live league's potential board and three draft classes). Each
keeps its legacy weights.

Per side, because legacy points don't mean the same WAR for a hitter and a
pitcher: 35 points was +0.7 WAR at bat and +2.1 on the mound. No hitter
reached 100 points, so his thresholds from there continue along the slope of
the top of his range.
"""
import inspect

from ranking.ledger import BATTING, PITCHING
from ranking.profiles import modifier_name
from utils.rank_graditated_model import RankGradiatedModel

# {modifier: {its weight model: {side: its thresholds in WAR}}}
WAR_THRESHOLDS = {
    # legacy points [0, 35, 55, 100, 130]
    "AgeModifier": {
        "modifier_weight_model": {BATTING: [-5.8, 0.7, 3.9, 10.3, 14.8], PITCHING: [-0.5, 2.1, 3.7, 6.7, 8.7]},
    },
    "DraftSecondaryPersonalityModifier": {
        # [0, 10, 35, 50, 75, 100]
        "bad_personality_modifier_model": {
            BATTING: [-5.8, -2.5, 0.7, 3.1, 6.6, 10.3], PITCHING: [-0.5, 0.5, 2.1, 3.3, 5.0, 6.7],
        },
        # [0, 25, 32, 40, 45]
        "high_leadership_modifier_model": {
            BATTING: [-5.8, -0.1, 0.3, 1.6, 2.4], PITCHING: [-0.5, 1.6, 2.0, 2.4, 2.9],
        },
        # [0, 30, 38]
        "low_leadership_modifier_model": {BATTING: [-5.8, 0.2, 1.2], PITCHING: [-0.5, 1.9, 2.4]},
    },
}


def in_war(modifier, side):
    """`modifier` (a legacy modifier class or instance) as v2 runs it on
    `side`: itself, or, when it weights by the score, a subclass of the same
    name whose weight models read WAR."""
    thresholds = WAR_THRESHOLDS.get(modifier_name(modifier))
    if thresholds is None:
        return modifier
    assert inspect.isclass(modifier), f"{modifier_name(modifier)} is configured; convert its instance"
    models = {
        attr: RankGradiatedModel(by_side[side], getattr(modifier, attr).vals)
        for attr, by_side in thresholds.items()
    }
    return type(modifier.__name__, (modifier,), models)
