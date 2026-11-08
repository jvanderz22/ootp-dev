"""Hitter platoons (ranking/stages/value.py) and their expected splits
(ranking/hitter_talent.py): you platoon your roster, so a hitter starts a side
in proportion to how close he is to an average regular there."""
import csv
import io

import numpy as np
import pytest

from models.game_players import PLAYER_FIELDS, GamePlayer
from ranking import get_ranker, hitter_talent
from ranking.ledger import MODIFIERS
from tests.e2e_fixtures import make_draft_class_csv

_BATTING = ("babip", "avoid_k", "gap", "power", "eye")


def _hitter(bats, level, pid):
    rows = csv.DictReader(io.StringIO(make_draft_class_csv(n=80, seed=7)))
    row = dict(next(r for r in rows if r["POS"] == "LF"), ID=str(pid), B=bats, WE="N", INT="N", Prone="Normal")
    for f in _BATTING:
        row[PLAYER_FIELDS[f]] = row[PLAYER_FIELDS[f + "_ovr"]] = str(level)
    return GamePlayer(row)


def _ranked(method, levels=(45, 50, 65)):
    players = [_hitter(b, lvl, 900000 + 10 * i + j)
               for i, lvl in enumerate(levels) for j, b in enumerate(("Left", "Right", "Switch"))]
    out = {}
    for r in get_ranker(method).rank(players):
        out[(r.position, int(r.id))] = r
    return {(b, lvl): out[("LF", 900000 + 10 * i + j)]
            for i, lvl in enumerate(levels) for j, b in enumerate(("Left", "Right", "Switch"))}


def _war(r):
    return (r.pre_demand_score - 50) / 10


def _platoon(r):
    return [line for line in r.ledger.lines if line.label.startswith("platoon")]


def test_an_average_lefty_is_the_strong_side_of_a_platoon():
    ranked = _ranked("potential")
    assert _war(ranked["Left", 50]) > _war(ranked["Right", 50])


def test_a_regular_on_both_sides_isnt_platooned():
    ranked = _ranked("potential")
    assert not any(_platoon(ranked[b, 65]) for b in ("Left", "Right", "Switch"))


def test_a_bat_below_replacement_on_both_sides_sits():
    ranked = _ranked("potential")
    assert all(_war(ranked[b, 45]) == pytest.approx(0, abs=0.01) for b in ("Left", "Right", "Switch"))


def test_switch_hitting_prospects_get_a_lineup_flexibility_factor():
    def switch_lines(method):
        r = _ranked(method)["Switch", 65]
        return [line for line in r.ledger.lines if line.label.startswith("switch hitter")]

    assert switch_lines("potential") and not switch_lines("overall")


def test_v2_drops_the_legacy_handedness_modifier():
    for r in _ranked("potential").values():
        assert not [line for line in r.ledger.lines
                    if line.stage == MODIFIERS and line.label == "BatterHandednessModifier"]


@pytest.mark.parametrize("bats", ["R", "L", "S"])
def test_expected_splits_blend_back_to_the_combined_rating(bats):
    model = hitter_talent.load()
    combined = dict.fromkeys(hitter_talent.RATINGS, np.array([50.0]))
    sides = model.expected_sides(combined, [bats])
    share = model.lhp_share([bats])
    blended = share * model.wrc_of(model.events(sides["vL"])) + (1 - share) * model.wrc_of(model.events(sides["vR"]))
    assert blended[0] == pytest.approx(model.wrc_plus(combined)[0], abs=2)
    gap = model.wrc_of(model.events(sides["vL"]))[0] - model.wrc_of(model.events(sides["vR"]))[0]
    assert (gap < 0) if bats == "L" else (gap > 0) if bats == "R" else abs(gap) < 10
