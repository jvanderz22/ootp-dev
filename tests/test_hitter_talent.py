"""The fitted hitter talent layer (phase 3): the model's tables, the ratings view,
and the v2 stage that replaces the legacy batting component."""
import numpy as np
import pytest

from league_snapshot import join_rows
from models.game_players import GamePlayer
from ranking import get_ranker, hitter_talent
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


def test_ratings_view_needs_babip(snapshot_rows):
    row = dict(next(r for r in snapshot_rows if r.get("BABIP")))
    row["BABIP"] = ""
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
        # fielding, running and the pitching side are the legacy ones
        assert r.fielding_score_component == base.fielding_score_component
        assert r.running_score_component == base.running_score_component
        assert r.pitcher_score == base.pitcher_score
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)
    assert changed


def test_breakdown_carries_the_fitted_batting_score(snapshot_rows):
    for r in _rank("overall", snapshot_rows, "v2"):
        talent = r.breakdown.get("batting", {}).get("talent")
        if talent:
            assert r.breakdown["batting"]["model"]["batting"] == pytest.approx(r.batting_score_component, abs=0.01)
            return
    pytest.fail("no player was scored by the talent layer")


def test_manifest_lists_the_artifact():
    assert get_ranker("overall").manifest()["artifact_versions"] == {"hitter-talent": hitter_talent.ARTIFACT}
    assert get_ranker("overall", "legacy").manifest()["artifact_versions"] == {}


def test_legacy_rankers_are_untouched(snapshot_rows):
    legacy = get_ranker_for_method("overall").rank([GamePlayer(dict(r)) for r in snapshot_rows], batch_size=1500)
    mirrored = _rank("overall", snapshot_rows, "legacy")
    assert [r.batting_score_component for r in legacy] == [r.batting_score_component for r in mirrored]
