"""Phase 5a: fielding (your grids, floors, calibrated to runs) and baserunning
(fitted, under optimal managing)."""
import json

import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import fielding_talent, get_ranker, running_talent
from ranking.fielding_talent import FLOOR_RAMP, FLOORS, POSITIONS, floor_factor, floored_grids
from ranking.stages.talent import FieldingTalent
from ranking.profiles import CURRENT
from tests.test_league_snapshot import make_snapshot_csvs


def _ratings(**over):
    base = dict.fromkeys(fielding_talent.RATINGS, 60)
    return {k: np.array([v]) for k, v in {**base, **over}.items()}


def test_floors_ramp_over_the_last_points_above_them():
    floor = FLOORS["SS"]["if_arm"]
    assert floor_factor("SS", _ratings(if_arm=floor + FLOOR_RAMP))[0] == 1
    assert floor_factor("SS", _ratings(if_arm=floor))[0] == pytest.approx(1 / 2)
    assert floor_factor("SS", _ratings(if_arm=floor - 5))[0] == 0
    assert floor_factor("SS", _ratings(if_arm=20))[0] == 0
    # the lowest floor rules; positions without floors are untouched
    assert floor_factor("SS", _ratings(if_arm=80, turn_dp=FLOORS["SS"]["turn_dp"] - 5))[0] == 0
    assert floor_factor("1B", _ratings(if_arm=20))[0] == 1


def test_a_weak_arm_takes_ss_and_3b_off_the_table():
    grids = {pos: np.array([60.0]) for pos in POSITIONS}
    floored = floored_grids(grids, _ratings(if_arm=30))
    assert floored["SS"][0] == floored["3B"][0] == 0
    assert floored["2B"][0] == floored["1B"][0] == 60


def test_value_rises_with_the_grid_and_a_grid_of_0_is_about_a_dh():
    model = fielding_talent.load()
    assert model.slope > 0
    dh = json.loads((fielding_talent.ARTIFACTS_DIR / f"{fielding_talent.ARTIFACT}.json").read_text())["dh_adjustment"]
    assert model.intercept == pytest.approx(dh, abs=3)


def test_harder_positions_are_worth_more():
    meta = json.loads((fielding_talent.ARTIFACTS_DIR / f"{fielding_talent.ARTIFACT}.json").read_text())["meta"]
    assert meta["rules"] and all(r["passed"] for r in meta["rules"].values())


def test_best_position_takes_the_adjustment():
    model = fielding_talent.load()
    same = {pos: np.array([50.0]) for pos in POSITIONS}
    value, best, runs = model.best(same)
    assert value[0] == pytest.approx(runs[0] + model.position_adjustment[best[0]])


def test_best_position_is_your_grids_pick_and_worth_the_most():
    # a good CF sits further above the LFs than the CFs, but CF grades higher
    model = fielding_talent.load()
    grids = {pos: np.array([0.0]) for pos in POSITIONS}
    grids.update(CF=np.array([60.0]), LF=np.array([55.0]))
    runs = model.runs(grids)
    assert runs["LF"][0] > runs["CF"][0]
    value, best, _ = model.best(grids)
    assert best == ["CF"]
    assert value[0] == max(v[0] for v in model.value(grids).values())


def test_utility_ignores_positions_below_their_floor():
    rows = [GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs()) if r["POS"] not in ("SP", "RP", "CL")]
    stage = FieldingTalent(CURRENT)
    for player in rows[:20]:
        (fit,) = stage.score([player])
        weak = GamePlayer({**player.attrs(), "IF ARM": "20", "OF ARM": "20", "TDP": "20"})
        (weak_fit,) = stage.score([weak])
        assert weak_fit.utility <= fit.utility


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


def test_v2_ledger_shows_fielding_utility_and_baserunning():
    rows = join_rows(*make_snapshot_csvs())
    for r in get_ranker("overall").rank([GamePlayer(dict(x)) for x in rows], batch_size=500):
        labels = [line.label for line in r.ledger.lines if line.side == "batting"]
        assert any(label.startswith("utility (") for label in labels)
        assert any(label.startswith("fielding (") for label in labels)
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)


def _cf(rng, arm=55, error=55):
    return fielding_talent.cf_grid({"of_range": [rng], "of_arm": [arm], "of_error": [error]})[0]


def test_cf_is_range_first():
    # 60 can't start, 65 playable, 70 good, 75 very good: each step is worth more than any arm or glove
    grades = [_cf(r) for r in (55, 60, 65, 70, 75, 80)]
    assert grades == sorted(grades)
    assert _cf(65, 80, 80) < _cf(70, 45, 35) and _cf(60, 80, 80) < _cf(65, 45, 35)


def test_cf_arm_and_error_only_count_at_the_edges():
    assert _cf(70, 45) == _cf(70, 50) == _cf(70, 60) == _cf(70)
    assert _cf(70, 40) < _cf(70) < _cf(70, 65)
    assert _cf(70, error=35) == _cf(70, error=80) == _cf(70)
    assert _cf(70, error=30) < _cf(70)
    # and even there, a little
    assert _cf(70) - _cf(70, 30, 25) < 6 and _cf(70, 80) - _cf(70) < 6
