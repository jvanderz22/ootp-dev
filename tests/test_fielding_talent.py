"""Fielding (lookup tables per position, your judged tables and floors, usage-
based position adjustments; 2026-11-09) and baserunning (fitted, under optimal
managing)."""
import json

import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import fielding_talent, get_ranker, running_talent
from ranking.fielding_talent import FLOOR_RAMP, FLOORS, POSITIONS, floor_factor, utility
from ranking.stages.talent import FieldingTalent
from ranking.profiles import CURRENT
from tests.test_league_snapshot import make_snapshot_csvs


def _ratings(**over):
    base = dict.fromkeys(fielding_talent.RATINGS, 60)
    return {k: np.array([v], float) for k, v in {**base, **over}.items()}


@pytest.fixture(scope="module")
def model():
    return fielding_talent.load()


def test_floors_ramp_over_the_last_points_above_them():
    floor = FLOORS["SS"]["if_arm"]
    assert floor_factor("SS", _ratings(if_arm=floor + FLOOR_RAMP))[0] == 1
    assert floor_factor("SS", _ratings(if_arm=floor))[0] == pytest.approx(1 / 2)
    assert floor_factor("SS", _ratings(if_arm=floor - 5))[0] == 0
    assert floor_factor("SS", _ratings(if_arm=20))[0] == 0
    # the lowest floor rules; positions without floors are untouched
    assert floor_factor("SS", _ratings(if_arm=80, turn_dp=FLOORS["SS"]["turn_dp"] - 5))[0] == 0
    assert floor_factor("1B", _ratings(if_arm=20))[0] == 1


def test_your_floors(model):
    # 2026-11-09: Turn DP 35 at 2B and 40 at SS; a catcher's Arm 35 and Blocking 45
    assert FLOORS["2B"]["turn_dp"] == 35 and FLOORS["SS"]["turn_dp"] == 40
    assert FLOORS["C"]["c_arm"] == 35 and FLOORS["C"]["c_blocking"] == 45


def test_below_a_floor_a_position_is_worth_a_dh(model):
    value = model.value(_ratings(if_arm=30))
    assert value["SS"][0] == value["3B"][0] == pytest.approx(model.dh_adjustment)
    assert value["2B"][0] > model.dh_adjustment


def test_runs_rise_with_every_rating(model):
    for pos, tables in model.tables.items():
        for rating, t in tables.items():
            assert np.all(np.diff(t) >= -1e-9), (pos, rating)


def test_harder_positions_are_worth_more():
    meta = json.loads((fielding_talent.ARTIFACTS_DIR / f"{fielding_talent.ARTIFACT}.json").read_text())["meta"]
    assert meta["rules"] and all(r["passed"] for r in meta["rules"].values())


def test_best_position_takes_the_adjustment_and_is_worth_the_most(model):
    ratings = _ratings(if_range=70, if_arm=70, if_error=65, turn_dp=60)
    value, best, runs = model.best(ratings)
    assert value[0] == pytest.approx(runs[0] + model.position_adjustment[best[0]])
    assert value[0] == max(v[0] for v in model.value(ratings).values())


def test_a_true_shortstop_is_worth_the_most_at_short(model):
    # 2026-11-09: StatsPlus's adjustments put SS 2 runs over 2B, so he went to 2B
    _, best, _ = model.best(_ratings(if_range=70, if_arm=70, if_error=65, turn_dp=60))
    assert best == ["SS"]


def _cf(model, rng, arm=55, error=55):
    return model.unfloored({**_ratings(), "of_range": np.array([rng], float), "of_arm": np.array([arm], float),
                            "of_error": np.array([error], float)})["CF"][0]


def test_cf_is_your_range_rule(model):
    # 60 can't start, 65 playable, 70 good, 75 very good: each step is worth more than any arm or glove
    runs = [_cf(model, r) for r in (55, 60, 65, 70, 75, 80)]
    assert runs == sorted(runs)
    assert _cf(model, 65, 80, 80) < _cf(model, 70, 45, 35) and _cf(model, 60, 80, 80) < _cf(model, 65, 45, 35)


def test_cf_arm_and_error_only_count_at_the_edges(model):
    assert _cf(model, 70, 45) == _cf(model, 70, 50) == _cf(model, 70, 60) == _cf(model, 70)
    assert _cf(model, 70, 40) < _cf(model, 70) < _cf(model, 70, 65)
    assert _cf(model, 70, error=35) == _cf(model, 70, error=80) == _cf(model, 70)
    assert _cf(model, 70, error=30) < _cf(model, 70)
    assert _cf(model, 70) - _cf(model, 70, 30, 25) < 6 and _cf(model, 70, 80) - _cf(model, 70) < 6


def test_an_arm_counts_most_in_right_and_least_in_left(model):
    # 2026-11-09: StatsPlus's arm runs can't see it, so it's your weight
    gain = {pos: model.tables[pos]["of_arm"][-1] - model.tables[pos]["of_arm"][fielding_talent.STEPS.index(60)]
            for pos in ("LF", "CF", "RF")}
    assert gain["RF"] > gain["CF"] > gain["LF"] > 0


def test_a_corner_outfielder_with_an_arm_is_worth_more_in_rf(model):
    # 2026-11-09: one corner skill apart from the arm, and RF a little more
    # valuable (a ball that gets by puts runners on third)
    from ranking.fitting.fielding_talent import RF_OVER_LF

    for rating in ("of_range", "of_error"):
        gap = np.asarray(model.tables["RF"][rating]) - np.asarray(model.tables["LF"][rating])
        assert np.ptp(gap) <= 0.02   # the tables are stored to 0.01
    assert model.position_adjustment["RF"] >= model.position_adjustment["LF"] + RF_OVER_LF - 1e-9

    def corner(arm):
        _, best, _ = model.best(_ratings(of_range=65, of_arm=arm, of_error=55, if_range=30, if_arm=30,
                                         if_error=30, turn_dp=30, c_arm=20, c_blocking=20, c_framing=20))
        return best[0]
    # a 45 or 50 arm plays LF (your call, 2026-11-09)
    assert corner(40) == corner(45) == corner(50) == "LF"
    assert corner(55) == corner(65) == corner(75) == "RF"


def test_utility_is_flexibility_not_runs():
    war, credited = utility({"SS", "3B", "CF", "LF"}, "2B")
    assert credited == ["SS", "3B", "CF"]
    assert war == pytest.approx(fielding_talent.UTILITY_WAR["SS"] + fielding_talent.UTILITY_WAR["3B"]
                                * fielding_talent.SS_COVERS_3B + fielding_talent.UTILITY_WAR["CF"])
    # only a position above his own in its group counts
    assert utility({"2B"}, "SS") == (0.0, [])
    assert utility({"CF"}, "LF")[1] == ["CF"]


def test_utility_ignores_positions_below_their_floor():
    rows = [GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs()) if r["POS"] not in ("SP", "RP", "CL")]
    stage = FieldingTalent(CURRENT)
    for player in rows[:20]:
        (fit,) = stage.score([player])
        weak = GamePlayer({**player.attrs(), "IF ARM": "20", "OF ARM": "20", "TDP": "20"})
        (weak_fit,) = stage.score([weak])
        assert weak_fit.utility_war <= fit.utility_war


def test_steals_are_never_negative_and_reward_good_stealers():
    model = running_talent.load()
    steal = np.arange(20, 81)
    runs = model.steal_runs({"steal": steal})
    assert np.all(runs >= 0) and runs[0] == 0 and runs[-1] > 5
    assert np.all(np.diff(runs) >= 0)


@pytest.mark.parametrize("rating", ["speed", "running_ability"])
def test_slow_runners_still_lose_extra_base_runs(rating):
    model = running_talent.load()
    ratings = {r: np.full(61, 50) for r in running_talent.RATINGS}
    ratings[rating] = np.arange(20, 81)
    runs = model.extra_base_runs(ratings)
    assert np.all(np.diff(runs) >= 0) and runs[0] < 0


def test_v2_ledger_shows_fielding_and_baserunning():
    rows = join_rows(*make_snapshot_csvs())
    for r in get_ranker("overall").rank([GamePlayer(dict(x)) for x in rows], batch_size=500):
        labels = [line.label for line in r.ledger.lines if line.side == "batting"]
        assert "fielding" in labels and "baserunning" in labels
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)
