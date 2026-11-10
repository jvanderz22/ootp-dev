"""Phase 5b: the value layer - talent -> WAR at a full-time role, shown as
50 + 10 x WAR."""
import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from models.player_type import HITTER, PITCHER, TWO_WAY, classify
from ranking import bridge, get_ranker, hitter_talent, value
from ranking.ledger import Ledger
from ranking.stages.demand import Demand
from ranking.stages.value import Value
from tests.test_league_snapshot import make_snapshot_csvs


@pytest.fixture(scope="module")
def model():
    return value.load()


@pytest.fixture(scope="module")
def ranked():
    return get_ranker("overall").rank([GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())], batch_size=500)


def test_display_points_put_replacement_at_50():
    assert value.points(0) == 50 and value.points(2.5) == 75


def test_starters_need_stamina_and_pitches_and_go_deeper_with_stamina(model):
    assert model.starter_innings(value.STARTER_MIN_STAMINA - 5, 4) == 0
    assert model.starter_innings(60, value.STARTER_MIN_PITCHES - 1) == 0
    innings = [model.starter_innings(s, 4) for s in (35, 50, 65, 80)]
    assert innings[0] > 0 and np.all(np.diff(innings) > 0)


def test_better_relievers_get_bigger_spots(model):
    leverage = model.leverage(np.array([70, 90, 100, 110, 130]))
    assert np.all(np.diff(leverage) < 0) and leverage[0] > 2 > 1 > leverage[-1]


def test_leverage_scales_runs_saved_either_way(model):
    good, bad = model.relieving(3.0, 75), model.relieving(5.5, 125)
    assert good["leverage"] > 0 and bad["leverage"] > 0  # below-average leverage softens his runs lost
    assert model.relieving(model.pitcher["league_era"], 100)["runs"] == pytest.approx(0)


def test_ledger_sums_to_the_score_from_replacement_level(ranked):
    for r in ranked:
        assert r.ledger.lines[0].label == "replacement level" and r.ledger.lines[0].delta == 50
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)


def test_modifiers_only_scale_war_above_replacement():
    state = type("S", (), {})()
    state.ledger, state.player = Ledger(), type("P", (), {"id": "x"})()
    side = type("Side", (), {"modifiers": [("Bad", 0.5)], "score": 0.0})()
    assert Value._modified(state, side, -1.0, "batting") == -1.0
    assert Value._modified(state, side, 2.0, "batting") == 1.0


def test_two_way_adds_a_share_of_the_other_side_above_replacement():
    state = type("S", (), {})()
    state.ledger = Ledger()
    Value._combine(state, 4.0, 3.0)
    assert state.value == pytest.approx(value.points(4.0 + value.TWO_WAY_SHARE * 3.0))
    state.ledger = Ledger()
    Value._combine(state, 3.0, -1.0)
    assert state.value == pytest.approx(value.points(3.0))
    assert not [line for line in state.ledger.lines if line.stage == "two-way"]


def test_demand_scales_only_the_value_above_replacement():
    result = type("R", (), {})()
    result.pre_demand_score, result.pre_demand_rank, result.ledger, result.breakdown = 70.0, 1, Ledger(), {}
    half = type("M", (), {"calculate_modified_score": staticmethod(lambda r, rank: 0.5)})()
    Demand(offset=value.DISPLAY_OFFSET).run([result], type("Pr", (), {"demand_modifiers": [half]})())
    assert result.overall_score == pytest.approx(60.0)


def test_players_below_replacement_on_both_sides_go_by_position():
    assert classify(-5, -20, "SS") == HITTER and classify(-20, -5, "SS") == HITTER
    assert classify(-5, -20, "RP") == PITCHER
    assert classify(30, 20, "SS") == TWO_WAY and classify(30, 10, "SP") == HITTER


def test_points_read_back_through_a_bridge():
    b = hitter_talent.load().bridge
    wrc = np.array([80.0, 100.0, 130.0])
    assert np.allclose(bridge.talent(bridge.points(wrc, b), b), wrc, atol=0.5)


def test_a_marginal_other_side_earns_no_two_way_credit():
    # a decent batter who'd be a back-end starter (Russ Knight, 1.0 WAR as an SP)
    assert value.two_way_share(1.0) == 0.0
    assert value.two_way_share(value.TWO_WAY_FLOOR) == 0.0
    # an average starter's worth or more gets the full share (Pat Farrell, 2.7)
    assert value.two_way_share(2.7) == value.TWO_WAY_SHARE
    between = value.two_way_share((value.TWO_WAY_FLOOR + value.TWO_WAY_FULL) / 2)
    assert between == pytest.approx(value.TWO_WAY_SHARE / 2)


# -- calibration, starters' depth and the Control floor (2026-11-08) ----------

def test_calibration_is_a_line_per_read(model):
    for name in ("wrc_plus", "baserunning"):
        a, b = model.calibration[name]
        assert model.calibrated(name, 10) == pytest.approx(a + 10 * b)
    # fielding: within the position (a level each, one stretch), apart from its adjustment
    field = model.calibration["fielding"]
    assert model.fielding_runs(5, "CF") == pytest.approx(field["by_position"]["CF"] + 5 * field["per_run"])
    a, b = field["value"]
    assert model.fielding_value(5, 2) == pytest.approx(a + 7 * b)
    for role in ("sp", "rp"):
        a, b = model.calibration["era"][role]
        assert model.calibrated("era", 4.0, role) == pytest.approx(a + 4 * b)
    assert value.ValueModel({**_bare(model), "calibration": None}).calibrated("wrc_plus", 123) == 123


def _bare(model):
    return {"version": model.version, "hitter": model.hitter, "pitcher": model.pitcher,
            "workloads": model.workloads, "leverage": model.leverage_map}


def test_efficient_starters_go_deeper_than_their_stamina(model):
    typical = model.workloads["ip_per_start"]["rates_at"]
    stingy = {**typical, "bb": typical["bb"] - 0.02, "hr": typical["hr"] - 0.008}
    wild = {**typical, "bb": typical["bb"] + 0.05}
    assert model.starter_innings(55, 4, stingy) > model.starter_innings(55, 4) > model.starter_innings(55, 4, wild)
    assert model.starter_innings(55, 4, typical) == pytest.approx(model.starter_innings(55, 4))


def test_control_floor_halves_at_the_floor_and_zeroes_a_step_below():
    f = value.CONTROL_FLOOR
    assert value.control_floor(f + value.FLOOR_RAMP) == 1
    assert value.control_floor(f) == pytest.approx(0.5)
    assert value.control_floor(f - value.FLOOR_RAMP) == 0


def test_a_wild_pitcher_keeps_none_of_his_value_above_replacement():
    from tests.test_pitcher_talent import _split_pitcher

    wild = _split_pitcher("Right", {"stuff_ovr": 70, "movement_ovr": 60, "control_ovr": 25,
                                    "hr_allowed_ovr": 60, "pbabip_ovr": 55})
    (r,) = get_ranker("overall").rank([wild])
    (line,) = [l for l in r.ledger.lines if l.label.startswith("Control floor")]
    assert line.side == "pitching" and "x0.00" in line.label
    assert r.pitcher_score <= 0
