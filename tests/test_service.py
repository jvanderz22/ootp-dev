"""Reading the stringified `components` dicts old ranked CSVs carry (db_import)."""
from db_import import _parse_components, legacy_breakdown


def test_parse_components_plain_repr():
    raw = "{'Pos - Batting Model': 51.2, 'Total Pos Modifier': 1.05}"
    assert _parse_components(raw) == {
        "Pos - Batting Model": 51.2,
        "Total Pos Modifier": 1.05,
    }


def test_parse_components_numpy2_scalar_repr():
    raw = (
        "{'Pos - Batting Model': np.float64(51.2), "
        "'Pos Modifier AgeModifier': np.float64(1.02), 'Pre Rank-adj Rank': 3}"
    )
    assert _parse_components(raw) == {
        "Pos - Batting Model": 51.2,
        "Pos Modifier AgeModifier": 1.02,
        "Pre Rank-adj Rank": 3,
    }


def test_parse_components_real_json():
    assert _parse_components('{"a": 1.5, "b": 2}') == {"a": 1.5, "b": 2}


def test_parse_components_empty_or_garbage():
    assert _parse_components("") == {}
    assert _parse_components(None) == {}
    assert _parse_components("this is not a dict ][") == {}


def test_legacy_breakdown_maps_every_current_key():
    raw = str({
        "Pos - Best Pos Score (SS)": 81.68, "Pos - Utility Bonus": 1,
        "Pos - Batting Model": 80.09, "Pos - Running Model": 92.65,
        "Pos - Overall Model Score": 80.09, "Pos Modifier AgeModifier": 1.02,
        "Total Pos Modifier": 1.08, "SP Pitcher Pitch Component": 0.9,
        "SP HR component": 0.97, "SP Model Score": 40.1, "SP Base Modifier": 0.8,
        "RP Model Score": 30.5, "RP Base Modifier": 0.7,
        "Starter Score w/Modifiers": 32.1, "Reliever Score w/Modifiers": 21.4,
        "Pitcher Modifier PitcherVelocityModifier": 0.95,
        "Total Pitcher Modifier": 0.95, "Rank-adj Modifier DraftDemandModifier": 0.9,
        "Pre Rank-adj Rank": 4, "Pre Rank-adj Score": 128.24,
    })
    assert legacy_breakdown(raw) == {
        "batting": {
            "model": {"best_position_score": 81.68, "utility_bonus": 1, "batting": 80.09,
                      "running": 92.65, "overall": 80.09},
            "modifiers": {"AgeModifier": 1.02},
            "modifier_total": 1.08,
        },
        "pitching": {
            "starter": {"pitch_mix": 0.9, "hr_risk": 0.97, "model": 40.1,
                        "base_modifier": 0.8, "score": 32.1},
            "reliever": {"model": 30.5, "base_modifier": 0.7, "score": 21.4},
            "modifiers": {"PitcherVelocityModifier": 0.95},
            "modifier_total": 0.95,
        },
        "rank_adjust": {"modifiers": {"DraftDemandModifier": 0.9}, "pre_rank": 4,
                        "pre_score": 128.24},
    }


def test_legacy_breakdown_keeps_retired_keys_on_their_side():
    raw = str({"Pitcher Adj Score": 3.1, "SP Starter Score w/Modifiers ": 4,
               "Pos - Something Old": 2, "Mystery": 1})
    assert legacy_breakdown(raw) == {
        "pitching": {"legacy": {"Pitcher Adj Score": 3.1, "SP Starter Score w/Modifiers ": 4}},
        "batting": {"legacy": {"Pos - Something Old": 2}},
        "legacy": {"Mystery": 1},
    }
