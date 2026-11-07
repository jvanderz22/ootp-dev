"""Engine v2 reproduces the legacy rankers exactly (the step 2a gate in
plans/ranking-v2-technical-plan.md): every ScoredPlayer field, breakdown and
order - plus a ledger that sums to the score and first-class pre-demand fields.

`legacy` is held to it everywhere, for good (it's how the eval explains a
legacy score). `v2` scores hitters with the fitted talent stage (phase 3) when
their BABIP is there, so it's held to it only where it isn't - the draft-class
fixtures, which are an old-format export - which is also its fallback test."""
import csv
import io

import pytest

from models.game_players import GamePlayer
from ranking import PIPELINES, PROFILES, get_ranker
from ranking.results import SCORED_PLAYER_FIELDS
from rankers.get_ranker import get_ranker_for_method
from tests.e2e_fixtures import make_draft_class_csv
from tests.test_league_snapshot import make_snapshot_csvs
from league_snapshot import join_rows


def _class_rows(seed):
    return list(csv.DictReader(io.StringIO(make_draft_class_csv(n=160, seed=seed))))


def _rank_both(method, rows, batch_size, pipeline="v2"):
    legacy = get_ranker_for_method(method).rank([GamePlayer(dict(r)) for r in rows], batch_size=batch_size)
    v2 = get_ranker(method, pipeline).rank([GamePlayer(dict(r)) for r in rows], batch_size=batch_size)
    return legacy, v2


def _fields(scored):
    return {name: getattr(scored, name) for name in SCORED_PLAYER_FIELDS}


@pytest.mark.parametrize("pipeline", sorted(PIPELINES))
@pytest.mark.parametrize("method", sorted(PROFILES))
@pytest.mark.parametrize("seed", [7, 11, 23])
def test_v2_matches_legacy_on_a_draft_class(method, seed, pipeline):
    # a batch size that doesn't divide the class exercises the batch boundary
    legacy, v2 = _rank_both(method, _class_rows(seed), batch_size=45, pipeline=pipeline)
    assert [_fields(s) for s in v2] == [_fields(s) for s in legacy]


@pytest.mark.parametrize("method", ["overall", "potential"])
def test_legacy_pipeline_matches_legacy_on_a_snapshot(method):
    legacy, v2 = _rank_both(method, join_rows(*make_snapshot_csvs()), batch_size=1500, pipeline="legacy")
    assert [_fields(s) for s in v2] == [_fields(s) for s in legacy]


@pytest.mark.parametrize("method", sorted(PROFILES))
def test_ledger_sums_to_the_score(method):
    _, v2 = _rank_both(method, _class_rows(7), batch_size=1500)
    for r in v2:
        assert r.ledger.total() == pytest.approx(r.overall_score, abs=1e-9), r.ledger.as_list()


def test_pre_and_post_demand_are_both_kept():
    legacy, v2 = _rank_both("draft_class", _class_rows(7), batch_size=1500)
    by_id = {r.id: r for r in v2}
    for r in legacy:
        mine = by_id[r.id]
        assert mine.pre_demand_score == r.raw_overall_score
        assert mine.pre_demand_rank == r.breakdown["rank_adjust"]["pre_rank"]
    assert [r.rank for r in v2] == list(range(1, len(v2) + 1))
    # demand actually moves someone in this class, so the two orders differ
    assert any(r.pre_demand_rank != r.rank for r in v2)


def test_manifest_names_what_produced_the_run():
    m = get_ranker("draft_class").manifest(source_version=3)
    assert m["engine"] == "v2" and m["pipeline"] == "v2" and m["profile"] == "draft_class"
    assert m["unit"] == "points"
    assert len(m["config_hash"]) == 12 and len(m["training_data_hash"]) == 12
    assert m["config_hash"] != get_ranker("overall").manifest()["config_hash"]


def test_unknown_method_is_an_error():
    with pytest.raises(ValueError):
        get_ranker("nope")
