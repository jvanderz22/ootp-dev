"""Pitcher matchups (ranking/value.py, ranking/stages/value.py) and the split
they follow (ranking/pitcher_talent.py): a reliever faces his strong side more,
a starter his weak side, by how big his split is - real, or predicted from
hand, slot and pitch mix."""
import pytest

from models.game_players import GamePlayer
from ranking import get_ranker, pitcher_talent, value
from ranking.ratings import RatingsView
from tests.test_pitcher_talent import _class_rows, _even, _score, _split_pitcher

# a right-hander far better against right-handed batters
_BIG = {"combined": _even(55), "vl": _even(42), "vr": _even(62)}


def _pitcher(position, split=_BIG, pid=990001, stamina=None):
    p = _split_pitcher("Right", split["combined"], split.get("vl"), split.get("vr"))
    # a third pitch, so he can start
    p._dict.update(POS=position, ID=str(pid), CB="55", CBP="55", **({"STM": str(stamina)} if stamina else {}))
    return GamePlayer(p._dict)


def _matchups(r):
    return [line for line in r.ledger.lines if "matchups" in line.label]


def test_the_tilt_ramps_with_the_split_either_way():
    assert value.matchup_tilt(0) == 0
    assert value.matchup_tilt(value.FULL_TILT_SPLIT / 2) == pytest.approx(value.MATCHUP_TILT / 2)
    assert value.matchup_tilt(-value.FULL_TILT_SPLIT) == value.matchup_tilt(3 * value.FULL_TILT_SPLIT) == value.MATCHUP_TILT


def test_a_split_is_how_much_better_he_is_against_his_own_hand():
    big, even = _score(_pitcher("RP")), _score(_pitcher("RP", {"combined": _even(55), "vl": _even(55), "vr": _even(55)}))
    assert big.rp_split > 10 and big.sp_split > 10 and not big.split_estimated
    assert even.rp_split == pytest.approx(0) and not even.split_estimated


def test_without_splits_the_split_is_predicted_from_slot_and_pitches():
    model = pitcher_talent.load()
    sidearm = pitcher_talent.split_features("R", "sidearm", {"sinker": 60, "slider": 60})
    over_top = pitcher_talent.split_features("R", "over the top", {"fastball": 60, "changeup": 60})
    assert model.predicted_split([sidearm])[0] > model.predicted_split([over_top])[0] + 5
    scored = _score(_split_pitcher("Right", _even(55)))
    assert scored.split_estimated and scored.rp_split == scored.sp_split != 0


def test_arm_slots_read_from_either_export():
    row = _class_rows()[0]
    for exported, slot in (("SIDE", "sidearm"), ("Sidearm", "sidearm"), ("Submarine", "sidearm"),
                           ("OTT", "over the top"), ("3/4", "normal"), ("Normal", "normal"), ("", "normal")):
        assert RatingsView.arm_slot(GamePlayer({**row, "Slot": exported})) == slot


def test_a_big_split_helps_a_reliever_and_costs_a_starter():
    ranked = {r.position: r for r in get_ranker("overall").rank([_pitcher("RP", stamina=20), _pitcher("SP", pid=990002)])}
    (rp_line,), (sp_line,) = _matchups(ranked["RP"]), _matchups(ranked["SP"])
    assert ranked["RP"].ledger.role == "RP" and "strong side" in rp_line.stat and rp_line.delta > 0
    assert ranked["SP"].ledger.role == "SP" and "weak side" in sp_line.stat and sp_line.delta < 0
    for r in ranked.values():
        counted = sum(line.delta for line in r.ledger.lines if r.ledger.counted(line) and line.stage != "demand")
        assert counted == pytest.approx(r.pre_demand_score, abs=0.05)


def test_a_big_split_moves_a_back_end_starter_to_the_bullpen(monkeypatch):
    back_end = {"combined": _even(45), "vl": _even(31), "vr": _even(52)}

    def role():
        (r,) = get_ranker("overall").rank([_pitcher("SP", back_end, stamina=35)])
        return r.ledger.role

    assert role() == "RP"
    monkeypatch.setattr(value, "MATCHUP_TILT", 0.0)
    assert role() == "SP"


def test_an_even_split_gets_no_matchups():
    even = {"combined": _even(55), "vl": _even(55), "vr": _even(55)}
    (r,) = get_ranker("overall").rank([_pitcher("RP", even)])
    assert not _matchups(r)
