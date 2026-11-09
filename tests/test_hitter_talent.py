"""The fitted hitter talent layer (phase 3): the model's tables, the ratings view,
and the v2 stage that replaces the legacy batting component."""
import csv
import io

import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import get_ranker, hitter_talent, pitcher_talent
from ranking.ratings import RatingsView
from rankers.get_ranker import get_ranker_for_method
from tests.test_league_snapshot import make_snapshot_csvs

# each component's direction in its rating
DIRECTION = {"k": -1, "bb": 1, "hr": 1, "hit": 1, "xbh": 1}


@pytest.fixture(scope="module")
def model():
    return hitter_talent.load()


@pytest.fixture(scope="module")
def snapshot_rows():
    return join_rows(*make_snapshot_csvs())


def _rank(method, rows, pipeline):
    return get_ranker(method, pipeline).rank([GamePlayer(dict(r)) for r in rows], batch_size=1500)


@pytest.mark.parametrize("component", sorted(DIRECTION))
def test_tables_are_monotone_in_their_rating(model, component):
    table = model.tables[component]
    assert len(table) == hitter_talent.HIGH - hitter_talent.LOW + 1
    assert np.all(DIRECTION[component] * np.diff(table) >= 0)
    assert np.all((table > 0) & (table < 1))


@pytest.mark.parametrize("rating", hitter_talent.RATINGS)
def test_a_higher_rating_never_lowers_wrc_plus(model, rating):
    base = dict.fromkeys(hitter_talent.RATINGS, 50)
    values = [model.wrc_plus({**base, rating: v}) for v in range(20, 81)]
    assert np.all(np.diff(values) >= 0)


def test_points_are_monotone_and_floored(model):
    wrc = np.linspace(-50, 300, 200)
    points = model.points(wrc)
    assert np.all(np.diff(points) >= 0) and points.min() == 0


def test_ratings_view_reads_the_profiles_side(snapshot_rows):
    player = next(GamePlayer(dict(r)) for r in snapshot_rows if r.get("BABIP"))
    current, potential = RatingsView("overall").hitting(player), RatingsView("potential").hitting(player)
    assert current["babip"] == player.babip_ovr and current["avoid_k"] == player.avoid_k_ovr
    assert potential["babip"] == player.babip and potential["power"] == player.power


def test_without_babip_the_view_reads_the_one_contact_implies(snapshot_rows):
    # Contact is about half BABIP and half Avoid K (every draft-class export lacks BABIP)
    row = dict(next(r for r in snapshot_rows if r.get("BABIP")))
    row.update({"BABIP": "", "CON": "55", "K's": "60", "HT P": "", "CON P": "70", "K P": "50"})
    player = GamePlayer(row)
    assert RatingsView("overall").hitting(player)["babip"] == 50
    assert RatingsView("potential").hitting(player)["babip"] == 80   # 90, held to the scale
    row.update({"CON": "", "K's": ""})
    assert RatingsView("overall").hitting(GamePlayer(row)) is None


@pytest.mark.parametrize("method", ["overall", "potential"])
def test_v2_scores_hitters_with_the_talent_layer(method, snapshot_rows, model):
    legacy = {r.id: r for r in _rank(method, snapshot_rows, "legacy")}
    players = {r["ID"]: GamePlayer(dict(r)) for r in snapshot_rows}
    view = RatingsView("overall" if method == "overall" else "potential")
    changed = 0
    for r in _rank(method, snapshot_rows, "v2"):
        base = legacy[r.id]
        labels = [line.label for line in r.ledger.lines]
        if view.hitting(players[r.id]):
            assert "batting model x0.73" not in labels
            assert any(label.startswith("batting talent (") for label in labels)
            changed += r.batting_score_component != base.batting_score_component
        # fielding and baserunning are fitted too (tests/test_fielding_talent.py)
        assert any(label.startswith("fielding (") for label in labels)
        assert any(label.startswith("baserunning (") for label in labels)
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)
    assert changed


def test_breakdown_carries_the_fitted_batting_score_and_war(snapshot_rows):
    for r in _rank("overall", snapshot_rows, "v2"):
        if r.breakdown.get("batting", {}).get("talent"):
            assert r.breakdown["batting"]["value"]["war"] == pytest.approx(r.position_player_score / 10, abs=0.01)
            return
    pytest.fail("no player was scored by the talent layer")


def test_manifest_lists_the_artifact():
    assert get_ranker("overall").manifest()["artifact_versions"] == {
        "hitter-talent": hitter_talent.ARTIFACT, "pitcher-talent": pitcher_talent.ARTIFACT,
        "fielding-talent": "fielding_talent_v1", "running-talent": "running_talent_v1", "value": "value_v1",
    }
    assert get_ranker("overall", "legacy").manifest()["artifact_versions"] == {}


def test_legacy_rankers_are_untouched(snapshot_rows):
    legacy = get_ranker_for_method("overall").rank([GamePlayer(dict(r)) for r in snapshot_rows], batch_size=1500)
    mirrored = _rank("overall", snapshot_rows, "legacy")
    assert [r.batting_score_component for r in legacy] == [r.batting_score_component for r in mirrored]


def _split_hitter(bats, combined, vl=None, vr=None):
    """A position player with current batting ratings `combined` ({field:
    value}) and, when given, vL / vR splits."""
    from models.game_players import PLAYER_FIELDS, split_header
    from tests.e2e_fixtures import make_draft_class_csv

    rows = csv.DictReader(io.StringIO(make_draft_class_csv(n=80, seed=7)))
    row = dict(next(r for r in rows if r["POS"] not in ("SP", "RP", "CL")))
    row["B"] = bats
    row.update({PLAYER_FIELDS[f]: str(v) for f, v in combined.items()})
    for side, ratings in (("vL", vl), ("vR", vr)):
        if ratings:
            row.update({split_header(f, side): str(v) for f, v in ratings.items()})
    return GamePlayer(row)


_BATTING = ("babip_ovr", "avoid_k_ovr", "gap_ovr", "power_ovr", "eye_ovr")


def _even(v):
    return dict.fromkeys(_BATTING, v)


def _score(player):
    from ranking.profiles import CURRENT
    from ranking.stages.talent import HitterTalent

    (scored,) = HitterTalent(CURRENT).score([player])
    return scored


def test_hitter_splits_equal_to_the_combined_ratings_score_the_same():
    plain = _score(_split_hitter("Right", _even(55)))
    split = _score(_split_hitter("Right", _even(55), _even(55), _even(55)))
    assert not plain.platoon and split.platoon
    assert split.wrc_plus == pytest.approx(plain.wrc_plus)


def test_a_hitter_is_judged_mostly_on_the_side_he_faces_more():
    # a lefty bats against right-handed pitchers about three times in four
    strong_vr = _score(_split_hitter("Left", _even(55), _even(45), _even(60)))
    strong_vl = _score(_split_hitter("Left", _even(55), _even(60), _even(45)))
    assert strong_vr.wrc_plus > strong_vl.wrc_plus


def test_righties_face_left_handed_pitchers_more_than_lefties():
    from ranking import hitter_talent

    mix = hitter_talent.load().platoon_mix
    assert mix["R"] > mix["S"] > mix["L"]
