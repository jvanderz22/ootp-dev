"""The fitted pitcher talent layer (phase 4): the model's tables, the Movement
fallback, the role factors kept until the value layer, and v2's pitching side."""
import csv
import io

import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import get_ranker, pitcher_talent
from ranking.ratings import RatingsView
from ranking.stages.talent import SP_ROLE_FLOOR, rp_role_factor, sp_role_factor
from tests.e2e_fixtures import make_draft_class_csv
from tests.test_league_snapshot import make_snapshot_csvs

# each component's direction in its rating
DIRECTION = {"k": 1, "bb": -1, "hr": -1, "hit": -1}


@pytest.fixture(scope="module")
def model():
    return pitcher_talent.load()


def _class_rows():
    return list(csv.DictReader(io.StringIO(make_draft_class_csv(n=80, seed=7))))


@pytest.mark.parametrize("role", pitcher_talent.ROLES)
@pytest.mark.parametrize("component", sorted(DIRECTION))
def test_tables_are_monotone_in_their_rating(model, role, component):
    tables = [model.tables[role][component]]
    if component in pitcher_talent.MOVEMENT_COMPONENTS:
        tables.append(model.movement_tables[role][component])
    for table in tables:
        assert np.all(DIRECTION[component] * np.diff(table) >= 0)
        assert np.all((table > 0) & (table < 1))


@pytest.mark.parametrize("role", pitcher_talent.ROLES)
@pytest.mark.parametrize("rating", ["stuff", "control", "hra", "pbabip", "movement"])
def test_a_higher_rating_never_allows_more_runs(model, role, rating):
    base = {"stuff": 50, "control": 50, "hra": 50, "pbabip": 50, "movement": 50}
    if rating == "movement":
        base.update(hra=None, pbabip=None)
    values = [model.runs_index({**base, rating: v}, role) for v in range(20, 81)]
    assert np.all(np.diff(values) <= 0)


def test_movement_stands_in_for_its_parts(model):
    parts = {"stuff": 50, "control": 50, "hra": 50, "pbabip": 50, "movement": 20}
    no_parts = {**parts, "hra": None, "pbabip": None}
    # Movement isn't read when HRA / PBABIP are there; it is when they aren't
    assert model.runs_index(parts, "sp") == model.runs_index({**parts, "movement": 80}, "sp")
    assert model.runs_index(no_parts, "sp") > model.runs_index({**no_parts, "movement": 80}, "sp")


def test_role_factors_keep_the_legacy_values():
    assert sp_role_factor(55, 4) == 1.0
    assert sp_role_factor(55, 2) == SP_ROLE_FLOOR  # 0.8 x 0.35 x 0.92, floored
    assert sp_role_factor(30, 5) == pytest.approx(0.7)
    assert sp_role_factor(55, 0) == rp_role_factor(55, 0) == 0.0
    assert rp_role_factor(55, 1) == pytest.approx(1.01 * 0.8)


def test_ratings_view_reads_the_profiles_side():
    row = next(r for r in join_rows(*make_snapshot_csvs()) if r.get("POS") == "SP")
    player = GamePlayer(dict(row))
    current, potential = RatingsView("overall").pitching(player), RatingsView("potential").pitching(player)
    assert current["stuff"] == player.stuff_ovr and current["hra"] == player.hr_allowed_ovr
    assert potential["stuff"] == player.stuff and potential["hra"] == player.hr_allowed


def test_a_class_without_hra_is_scored_on_movement():
    row = next(r for r in _class_rows() if r["POS"] == "SP")
    ratings = RatingsView("potential").pitching(GamePlayer(dict(row)))
    assert ratings["hra"] is None and ratings["pbabip"] is None and ratings["movement"]


def test_v2_scores_pitchers_with_the_talent_layer():
    for r in get_ranker("draft_class").rank([GamePlayer(dict(row)) for row in _class_rows()], batch_size=45):
        labels = [line.label for line in r.ledger.lines if line.side == "pitching"]
        assert any("talent (Stuff" in label and "ERA)" in label for label in labels), labels
        assert not any(label in ("SP model", "RP model") for label in labels)
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)


def test_a_pitcher_without_ratings_is_valued_at_replacement():
    row = dict(next(r for r in _class_rows() if r["POS"] == "SP"))
    row["STU P"] = row["STU"] = ""
    (r,) = get_ranker("draft_class").rank([GamePlayer(row)], batch_size=1)
    labels = [line.label for line in r.ledger.lines if line.side == "pitching"]
    # no legacy scorer behind it: the side says why it's worth replacement
    assert any("no pitching ratings" in label for label in labels), labels
    assert not any(" talent (" in label for label in labels)
    assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)


@pytest.mark.parametrize("side", ["overall", "potential"])
def test_relievers_gain_stuff_most_from_two_good_pitches(model, side):
    shift = model.stuff_shift([[70, 65, 40, 0], [60, 55, 50, 45]], side)
    assert np.all(shift >= 0) and shift[0] > shift[1]
    assert model.stuff_shift([[20, 0, 0, 0]], side)[0] == 0


@pytest.mark.parametrize("side", ["overall", "potential"])
def test_a_reliever_loses_more_stuff_as_a_starter_than_a_starter_gains_in_relief(model, side):
    top = [[70, 65, 40, 0]]
    as_sp = model.role_stuff([55], top, [True], side)
    as_rp = model.role_stuff([55], top, [False], side)
    assert as_sp["sp"][0] == 55 and as_rp["rp"][0] == 55
    gained, lost = as_sp["rp"][0] - 55, 55 - as_rp["sp"][0]
    assert gained > 0 and lost > gained  # the margin errs towards taking Stuff away


def test_v2_scores_a_listed_reliever_as_a_starter_on_less_stuff():
    from ranking.profiles import DRAFT
    from ranking.stages.talent import PitcherTalent

    row = dict(next(r for r in _class_rows() if r["POS"] == "SP"))
    stage = PitcherTalent(DRAFT)
    (sp,) = stage.score([GamePlayer(row)])
    (rp,) = stage.score([GamePlayer({**row, "POS": "RP"})])
    assert rp.sp_stuff < sp.sp_stuff and rp.sp_index > sp.sp_index
    assert rp.rp_stuff < sp.rp_stuff and rp.rp_index > sp.rp_index


# current pitching ratings, combined and per platoon side
_CURRENT = ("stuff_ovr", "movement_ovr", "control_ovr", "hr_allowed_ovr", "pbabip_ovr")


def _split_pitcher(throws, combined, vl=None, vr=None):
    """A listed SP with current ratings `combined` ({field: value}) and, when
    given, vL / vR splits."""
    from models.game_players import PLAYER_FIELDS, split_header

    row = dict(next(r for r in _class_rows() if r["POS"] == "SP"))
    row["T"] = throws
    row.update({PLAYER_FIELDS[f]: str(v) for f, v in combined.items()})
    for side, ratings in (("vL", vl), ("vR", vr)):
        if ratings:
            row.update({split_header(f, side): str(v) for f, v in ratings.items()})
    return GamePlayer(row)


def _even(v):
    return dict.fromkeys(_CURRENT, v)


def _score(player, profile=None):
    from ranking.profiles import CURRENT
    from ranking.stages.talent import PitcherTalent

    (scored,) = PitcherTalent(profile or CURRENT).score([player])
    return scored


def test_righties_face_more_left_handed_batters_than_lefties(model):
    for role in pitcher_talent.ROLES:
        assert model.platoon_mix[role]["R"] > model.platoon_mix[role]["L"]


def test_splits_equal_to_the_combined_ratings_score_the_same():
    plain = _score(_split_pitcher("Right", _even(55)))
    split = _score(_split_pitcher("Right", _even(55), _even(55), _even(55)))
    assert not plain.platoon and split.platoon
    assert split.sp_era == pytest.approx(plain.sp_era) and split.rp_index == pytest.approx(plain.rp_index)


def test_a_weak_side_costs_what_the_rounded_combined_rating_hides():
    # a lefty starter's line (Ben Hodge, 2042): Stuff 40 combined, but 35 vs
    # the right-handed batters he mostly faces
    combined = {"stuff_ovr": 40, "movement_ovr": 55, "control_ovr": 40, "hr_allowed_ovr": 60, "pbabip_ovr": 50}
    vl = {"stuff_ovr": 40, "movement_ovr": 60, "control_ovr": 45, "hr_allowed_ovr": 65, "pbabip_ovr": 50}
    vr = {"stuff_ovr": 35, "movement_ovr": 55, "control_ovr": 40, "hr_allowed_ovr": 55, "pbabip_ovr": 50}
    plain = _score(_split_pitcher("Left", combined))
    split = _score(_split_pitcher("Left", combined, vl, vr))
    assert split.sp_era > plain.sp_era + 0.1


def test_the_side_he_faces_more_weighs_more():
    good, bad = _even(60), _even(45)
    strong_vr = _score(_split_pitcher("Left", _even(50), bad, good))
    strong_vl = _score(_split_pitcher("Left", _even(50), good, bad))
    assert strong_vr.sp_era < strong_vl.sp_era   # a lefty mostly faces right-handed batters


def test_potential_ratings_have_no_splits():
    from ranking.profiles import POTENTIAL

    player = _split_pitcher("Right", _even(55), _even(60), _even(45))
    assert RatingsView("potential").pitching_splits(player) is None
    assert not _score(player, POTENTIAL).platoon


def test_tables_keep_improving_to_the_top_of_the_scale(model):
    # a table that ran out of data is continued, not left flat (HRA 80 beats 70)
    for role in pitcher_talent.ROLES:
        for name, t in model.tables[role].items():
            assert DIRECTION[name] * (t[-1] - t[-11]) > 0, (role, name)


def test_a_flat_top_is_continued_at_the_slope_below():
    from ranking.fitting.pitcher_talent import extend_tail

    flat = [0.05 - 0.001 * i for i in range(40)] + [0.011] * 21
    extended = extend_tail(flat)
    assert extended[:40] == pytest.approx(flat[:40], abs=1e-5)
    assert np.all(np.diff(extended[39:]) < 0)
    rising = list(np.linspace(0.1, 0.3, 61))
    assert extend_tail(rising) == pytest.approx(rising, abs=1e-5)
