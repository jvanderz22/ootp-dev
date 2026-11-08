"""The development layer's makeup / durability factors (ranking/development.py)."""
import csv
import io

import pytest

from models.game_players import GamePlayer
from ranking import development, get_ranker
from ranking.ledger import DEMAND, DEVELOPMENT, MODIFIERS
from tests.e2e_fixtures import make_draft_class_csv


def _player(we="N", intelligence="N", prone="Normal"):
    return type("P", (), {"work_ethic": we, "intelligence": intelligence, "injury_prone": prone})()


def _product(player, war):
    out = 1.0
    for _, factor in development.factors(player, war):
        out *= factor
    return out


def test_factors_apply_in_full_below_the_taper_and_fade_above_it():
    assert development.weight(development.FULL_WEIGHT_WAR) == 1.0
    assert development.weight(development.TAPERED_WAR) == pytest.approx(development.TAPERED_WEIGHT)
    assert development.weight(20) == pytest.approx(development.TAPERED_WEIGHT)
    assert _product(_player(we="H"), 1.0) == pytest.approx(1.25)
    assert _product(_player(we="H"), 8.0) == pytest.approx(1.25 ** development.TAPERED_WEIGHT)


def test_ordinary_makeup_moves_nothing():
    assert development.factors(_player(), 2.0) == []


def test_maxed_makeup_cant_lift_a_mediocre_prospect_over_a_generational_one():
    maxed = _player(we="H", intelligence="H", prone="Iron Man")
    assert 4.5 * _product(maxed, 4.5) < 6.0 * _product(_player(), 6.0)


def _class_rows():
    return list(csv.DictReader(io.StringIO(make_draft_class_csv(n=80, seed=7))))


def test_v2_develops_prospects_in_place_of_the_legacy_makeup_and_injury_modifiers():
    ranked = get_ranker("draft_class").rank([GamePlayer(dict(r)) for r in _class_rows()], batch_size=40)
    replaced = set(development.REPLACES)
    assert not [l for r in ranked for l in r.ledger.lines if l.stage == MODIFIERS and l.label in replaced]
    developed = [r for r in ranked if any(l.stage == DEVELOPMENT for l in r.ledger.lines)]
    assert developed
    for r in developed:
        before_demand = [l for l in r.ledger.lines if r.ledger.counted(l) and l.stage != DEMAND]
        assert sum(l.delta for l in before_demand) == pytest.approx(r.pre_demand_score)


def test_current_ratings_have_no_development():
    ranked = get_ranker("overall").rank([GamePlayer(dict(r)) for r in _class_rows()], batch_size=40)
    assert not [l for r in ranked for l in r.ledger.lines if l.stage == DEVELOPMENT]
