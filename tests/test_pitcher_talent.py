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
        assert any("talent (runs allowed" in label for label in labels), labels
        assert not any(label in ("SP model", "RP model") for label in labels)
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9)
        assert r.starter_component >= 0 and r.reliever_component >= 0


def test_a_pitcher_without_ratings_falls_back_to_legacy():
    row = dict(next(r for r in _class_rows() if r["POS"] == "SP"))
    row["STU P"] = row["STU"] = ""
    (r,) = get_ranker("draft_class").rank([GamePlayer(row)], batch_size=1)
    labels = [line.label for line in r.ledger.lines if line.side == "pitching"]
    assert {"SP model", "RP model"} & set(labels)
