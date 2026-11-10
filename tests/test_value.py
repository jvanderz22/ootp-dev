"""Phase 5b: the value layer - talent -> WAR at a full-time role, shown as
50 + 10 x WAR."""
import csv
import io

import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from models.player_type import HITTER, PITCHER, TWO_WAY, classify
from ranking import get_ranker, value
from ranking.ledger import Ledger
from ranking.state import PlayerState
from ranking.stages.demand import Demand
from ranking.stages.value import Value
from tests.e2e_fixtures import make_draft_class_csv
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
    state = PlayerState(player=None)
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
    (line,) = [l for l in r.ledger.lines if l.label == "Control floor"]
    assert line.side == "pitching" and line.stat == "x0.00"
    assert r.pitcher_score <= 0


# -- the league's replacement (2026-11-10) ---------------------------------------

SPOTS = {"lineup_shares": [0.67, 0.6, 0.5, 0.43, 0.37], "bullpen_leverage": [1.9, 1.5, 1.3, 1.15, 1.0, 0.9, 0.8, 0.7],
         "bullpen_tilt": [0.0, 0.0, 0.05, 0.05, 0.06, 0.06, 0.06, 0.06]}


def test_spots_taper_playing_time_and_leverage():
    rep = value.Replacement(SPOTS)
    bats = rep.hitter_spots(2.0)
    assert bats["H"] == 2.0 and bats["H8"] == pytest.approx(1.34) and bats["H12"] == pytest.approx(0.74)
    pen = rep.relief_spots(1.0, 0.3, 0.42)
    assert pen["RP1"] > pen["RP4"] > pen["RP8"] and pen["RP5"] == pytest.approx(1.3)
    assert set(value.spot_slots(30)) == {*bats, *pen, "SP"} and value.spot_slots(30)["H"] == 30 * value.LINEUP_FULL


def test_a_player_is_valued_at_the_spot_hes_furthest_above_its_price():
    prices = {**dict.fromkeys(value.spot_slots(1), 0.2), "H": 1.7, "H8": 1.0, "SP": 2.0}
    rep = value.Replacement(SPOTS, {**prices, **dict.fromkeys(("H9", "H10", "H11", "H12"), 1.0)})
    assert rep.best(rep.hitter_spots(4.0)) == "H"
    assert rep.best(rep.hitter_spots(2.0)) == "H8"   # 2.0 - 1.7 < 1.34 - 1.0
    assert rep.best({"SP": 2.1, **rep.relief_spots(1.0, 0.3, 0.42)}) == "RP1"


def test_spot_prices_are_what_the_next_best_player_would_add():
    from ranking.fitting.replacement import prices

    players = [{"H": w, "H8": 0.5 * w} for w in (4.0, 3.5, 3.0, 2.0, 1.0)]
    # one everyday spot and two half-time: 4 starts, 3.5 and 3 sit, 2 and 1 are out
    got = prices(players, {"H": 1, "H8": 2})

    def net(p):
        return {s: p[s] - got[s] for s in p}

    assert max(net(players[0]), key=net(players[0]).get) == "H"
    assert all(max(net(p).values()) >= -1e-9 and max(net(p), key=net(p).get) == "H8" for p in players[1:3])
    assert all(max(net(p).values()) <= 1e-9 for p in players[3:])


def test_only_current_ratings_use_the_league_replacement(ranked):
    def lines(r):
        return [line for line in r.ledger.lines if line.label == "league replacement"]

    if value.replacement() is None:
        pytest.skip("no replacement artifact")
    assert all(len(lines(r)) >= 1 for r in ranked)
    potential = get_ranker("potential").rank([GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())])
    assert not any(lines(r) for r in potential)


def test_a_bat_below_replacement_everywhere_is_valued_full_time(ranked):
    for r in ranked:
        if r.ledger.side == "batting" and r.overall_score < value.DISPLAY_OFFSET:
            assert not [line for line in r.ledger.lines if line.label == "playing time" and r.ledger.counted(line)]


def test_two_way_never_takes_off_for_a_side_below_the_league_price():
    state = PlayerState(player=None)
    state.pitching.replacement = 2.0   # 1.8 WAR starting, 0.2 under the rotation's price
    Value._combine(state, 3.0, -0.2)
    assert state.value == pytest.approx(value.points(3.0))


def test_the_full_time_profile_is_current_ratings_without_roster_pricing():
    # the Current card's full-time line, and the draft odds' outcome A and
    # readiness (plans/draft-odds-plan.md): the potential and draft boards' conventions
    from ranking.profiles import CURRENT, FULL_TIME

    differ = {k for k, v in FULL_TIME.describe().items() if CURRENT.describe()[k] != v}
    assert differ == {"name", "league_replacement", "companions"} and not FULL_TIME.companions
    full_time = get_ranker("full_time")
    stage = next(s for s in full_time.batch_stages if isinstance(s, Value))
    assert stage.replacement is None and "replacement" not in full_time.manifest()["artifact_versions"]
    for r in full_time.rank([GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())]):
        assert not [line for line in r.ledger.lines if line.label in ("league replacement", "playing time")]
        # a reliever's leverage is his talent's, not a bullpen spot's
        assert all(line.note is None for line in r.ledger.lines if line.label == "leverage")
        assert r.replacement is None


def test_the_ceiling_is_his_potential_ratings_alone():
    from ranking.ledger import DEVELOPMENT, MODIFIERS
    from ranking.profiles import CEILING
    from ranking.ranker import Ranker

    rows = join_rows(*make_snapshot_csvs())
    alone = {r.id: r for r in Ranker(CEILING).rank([GamePlayer(dict(r)) for r in rows])}
    assert not any(line.stage in (MODIFIERS, DEVELOPMENT) for r in alone.values() for line in r.ledger.lines)
    for method in ("overall", "potential"):
        for r in get_ranker(method).rank([GamePlayer(dict(r)) for r in rows]):
            war = (alone[r.id].pre_demand_score - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE
            assert r.ceiling_war == pytest.approx(war, abs=0.006), (method, r.name)
    # the draft board's ceiling is its own model lines (the draft odds, step C)
    draft = csv.DictReader(io.StringIO(make_draft_class_csv(n=40, seed=7)))
    assert all(r.ceiling_war is None for r in get_ranker("draft_class").rank([GamePlayer(r) for r in draft]))


def test_current_ratings_carry_his_full_time_war(ranked):
    rows = join_rows(*make_snapshot_csvs())
    full_time = {r.id: r for r in get_ranker("full_time").rank([GamePlayer(dict(r)) for r in rows])}
    for r in ranked:
        alone = full_time[r.id]
        assert r.full_time_war == pytest.approx((alone.pre_demand_score - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE, abs=0.006)
        assert r.full_time_role == alone.role
        if r.replacement is not None and r.role == alone.role and not [
            line for line in r.ledger.lines if line.label == "playing time" and r.ledger.counted(line)
        ] and r.role not in ("RP",):
            # an everyday bat or a starter: the roster takes only its price
            war = (r.pre_demand_score - value.DISPLAY_OFFSET) / value.DISPLAY_SCALE + r.replacement
            assert r.full_time_war == pytest.approx(war, abs=0.02), r.name
    assert get_ranker("potential").rank([GamePlayer(dict(r)) for r in rows])[0].full_time_war is None


def test_the_ceiling_leaves_the_card_alone(ranked):
    # the companion scores in its own breakdown scope
    from dataclasses import replace

    from ranking.profiles import CURRENT
    from ranking.ranker import Ranker

    plain = Ranker(replace(CURRENT, companions=())).rank(
        [GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())], batch_size=500)
    assert [(r.id, r.breakdown, r.overall_score) for r in plain] == [(r.id, r.breakdown, r.overall_score) for r in ranked]


def test_a_reliever_picks_fewer_matchups_in_a_busier_spot():
    rep = value.Replacement(SPOTS)
    half, full = rep.tilts(value.FULL_TILT_SPLIT / 2), rep.tilts(-2 * value.FULL_TILT_SPLIT)
    assert full == pytest.approx(list(value.RELIEF_TILT)) and full[0] < full[2] < full[4]
    assert half[4] == pytest.approx(full[4] / 2) and max(full) < value.MATCHUP_TILT
    # more runs saved a spot (his matchups) count at that spot's leverage
    pen = rep.relief_spots([1.0] * 4 + [2.0] * 4, 0.3, 0.42)
    assert pen["RP5"] == pytest.approx(2.0 * 1.0 + 0.3)
