"""The legacy modifiers v2 keeps, weighted by WAR (ranking/modifiers.py), and
v2's pipeline running without the legacy scorers (plans/xgboost-phaseout-plan.md,
step 3)."""
import pytest

from models.game_players import GamePlayer
from modifiers.age_modifier import AgeModifier
from modifiers.draft_secondary_personality_modifier import DraftSecondaryPersonalityModifier
from ranking import PROFILES, get_ranker
from ranking.ledger import BATTING, PITCHING
from ranking.modifiers import WAR_THRESHOLDS, in_war
from ranking.profiles import modifier_name
from modifiers.scouting_accuracy_modifier import ScoutingAccuracyModifier

LEGACY = {"AgeModifier": AgeModifier, "DraftSecondaryPersonalityModifier": DraftSecondaryPersonalityModifier}


@pytest.mark.parametrize("side", [BATTING, PITCHING])
def test_converted_modifiers_keep_their_name_and_weights(side):
    for name, models in WAR_THRESHOLDS.items():
        legacy = LEGACY[name]
        weighted = in_war(legacy, side)
        assert modifier_name(weighted) == name and issubclass(weighted, legacy)
        for attr, by_side in models.items():
            model = getattr(weighted, attr)
            assert model.vals == getattr(legacy, attr).vals
            assert model.ranks == by_side[side] and model.ranks == sorted(model.ranks)
            assert len(model.ranks) == len(getattr(legacy, attr).ranks)


def test_modifiers_that_ignore_the_score_are_untouched():
    assert in_war(ScoutingAccuracyModifier, BATTING) is ScoutingAccuracyModifier


def test_a_threshold_in_war_weights_as_its_points_did():
    # an 18-year-old: half his age bonus at 55 points, which is +3.9 WAR at bat
    # and +3.7 on the mound
    player = GamePlayer({"Age": "18"})
    half = AgeModifier.calculate_player_modifier(player, 55)
    assert half == pytest.approx(1.12 ** 0.5)
    assert in_war(AgeModifier, BATTING).calculate_player_modifier(player, 3.9) == pytest.approx(half)
    assert in_war(AgeModifier, PITCHING).calculate_player_modifier(player, 3.7) == pytest.approx(half)
    # a weak prospect gets all of it on either side
    assert in_war(AgeModifier, BATTING).calculate_player_modifier(player, 0.0) == pytest.approx(1.12)


@pytest.mark.parametrize("method", sorted(PROFILES))
def test_v2_runs_the_talent_models_and_values_them_in_war(method):
    ranker = get_ranker(method)
    assert [s.name for s in ranker.batch_stages] == ["talent", "value"]
