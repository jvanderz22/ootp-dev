from web.service import _parse_components


def test_parse_components_plain_repr():
    raw = "{'Pos Modifier AgeModifier': 1.02, 'Total Pos Modifier': 1, 'x': 0.9}"
    assert _parse_components(raw) == {
        "Pos Modifier AgeModifier": 1.02,
        "Total Pos Modifier": 1,
        "x": 0.9,
    }


def test_parse_components_numpy2_scalar_repr():
    """NumPy >= 2 bakes `np.float64(...)` / `np.int64(...)` into a dict's repr;
    the reader must still recover the values (see the prod modifier-panel bug)."""
    raw = (
        "{'Pitcher Modifier AgeModifier': np.float64(1.03), "
        "'Total Pitcher Modifier': np.float64(0.9), "
        "'Pos Modifier X': np.int64(1)}"
    )
    assert _parse_components(raw) == {
        "Pitcher Modifier AgeModifier": 1.03,
        "Total Pitcher Modifier": 0.9,
        "Pos Modifier X": 1,
    }


def test_parse_components_real_json():
    assert _parse_components('{"a": 1.5, "b": 2}') == {"a": 1.5, "b": 2}


def test_parse_components_empty_or_garbage():
    assert _parse_components("") is None
    assert _parse_components(None) is None
    assert _parse_components("this is not a dict ][") is None
