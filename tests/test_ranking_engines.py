"""Runs kept per ranking engine (ranking_engine.py): the schema v3 migration,
per-engine storage with v2's ledger and pre-demand fields, scoring a class under
every engine, and the app's X-Ranking-Engine toggle."""
import sqlite3

import pytest

import ranking_engine
import results_store

CLASS = "engines-fx"


@pytest.fixture
def fixture_class(data_dir):
    from context import DraftClassContext
    from tests.e2e_fixtures import make_draft_class_csv

    (data_dir / "datasets").mkdir(parents=True)
    (data_dir / "processed_classes" / CLASS).mkdir(parents=True)
    (data_dir / "datasets" / f"{CLASS}.csv").write_text(make_draft_class_csv(n=80, seed=11))
    ctx = DraftClassContext(CLASS)
    ctx.register("draft_class")
    return ctx


def test_migration_3_keeps_existing_runs_as_legacy(data_dir):
    import db

    path = data_dir / db.DB_FILENAME
    conn = sqlite3.connect(path)
    db._run_script(conn, db._SCHEMA_V1)
    db._run_script(conn, db._SCHEMA_V2)
    conn.execute(
        "INSERT INTO model_runs VALUES ('class', 'c', 'draft_class', 3, '2042-01-01', 1)"
    )
    conn.execute(
        "INSERT INTO run_results (scope, scope_id, method, player_id, model_rank, "
        "player_type, model_score, breakdown) VALUES "
        "('class', 'c', 'draft_class', '7', 1, 'Hitter', 51.5, '{}')"
    )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    assert db.query_one("PRAGMA user_version")[0] == len(db._MIGRATIONS) == 7
    info = results_store.run_info("class", "c", "draft_class", "legacy")
    assert info["source_version"] == 3 and info["manifest"] is None
    assert results_store.run_info("class", "c", "draft_class", "v2") is None
    (row,) = results_store.load_results("class", "c", "draft_class", engine="legacy")
    assert row["model_score"] == 51.5 and row["pre_demand_score"] is None
    # the old tables and their index are gone, the new index is in place
    tables = {r[0] for r in db.query("SELECT name FROM sqlite_master")}
    assert "model_runs_v2" not in tables and "run_results_v2" not in tables
    assert "run_results_order" in tables
    # deleting a run still cascades to its results
    results_store.delete_runs("class", "c")
    assert db.query_one("SELECT COUNT(*) FROM run_results")[0] == 0


def test_engines_store_separate_runs(fixture_class):
    from pipeline import process_class

    process_class(fixture_class)
    v2 = results_store.class_results(fixture_class, with_breakdown=True, engine="v2")
    legacy = results_store.class_results(fixture_class, with_breakdown=True, engine="legacy")
    # the same players, scored by different engines
    assert {r["id"] for r in v2} == {r["id"] for r in legacy}
    assert [r["model_score"] for r in v2] != [r["model_score"] for r in legacy]
    # v2 adds the pre-demand fields and the ledger; legacy has neither
    assert all(r["pre_demand_rank"] for r in v2)
    assert all(r["pre_demand_score"] is None and r["ledger"] is None for r in legacy)
    top = v2[0]
    counted = [line for line in top["ledger"]["lines"] if line[3] in (None, top["ledger"]["side"])]
    assert sum(line[2] for line in counted) == pytest.approx(top["model_score"], abs=0.01)
    manifest = results_store.run_info("class", CLASS, "draft_class", "v2")["manifest"]
    assert manifest["engine"] == "v2" and manifest["profile"] == "draft_class"
    # a legacy run has no manifest of its own, just the model version
    legacy_manifest = results_store.run_info("class", CLASS, "draft_class", "legacy")["manifest"]
    assert set(legacy_manifest) == {"model_version"} == set(manifest) & {"model_version"}


def test_a_class_missing_the_current_engine_is_scored_on_read(fixture_class):
    from pipeline import class_results, write_player_scores, load_player_data

    # processed before v2 existed: only a legacy run
    write_player_scores(fixture_class, load_player_data(fixture_class), "legacy")
    assert results_store.class_results(fixture_class, engine="v2") is None
    rows = class_results(fixture_class)  # served under the default engine, v2
    assert rows and rows[0]["pre_demand_rank"] is not None
    assert results_store.run_info("class", CLASS, "draft_class", "v2") is not None


def test_an_unprocessed_class_stays_unprocessed(fixture_class):
    from pipeline import class_results

    assert class_results(fixture_class) is None


def test_using_scopes_the_engine():
    assert ranking_engine.current() == ranking_engine.DEFAULT_ENGINE == "v2"
    with ranking_engine.using("legacy"):
        assert ranking_engine.current() == "legacy"
    assert ranking_engine.current() == "v2"
    with pytest.raises(ValueError):
        ranking_engine.validate("v3")


# ------------------------------------------------------------------ the app
@pytest.fixture
def client(fixture_class, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    from starlette.testclient import TestClient

    from pipeline import process_class
    from web.app import app

    process_class(fixture_class)
    return TestClient(app)


def _gql(client, query, engine=None, **variables):
    headers = {"X-Ranking-Engine": engine} if engine else {}
    resp = client.post("/graphql", json={"query": query, "variables": variables}, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    assert "errors" not in body, body["errors"]
    return body["data"]


_ROWS = f"""{{ rankedPlayers(name: "{CLASS}", pageSize: 5)
  {{ rows {{ id modelScore preDemandScore preDemandRank source {{ engine }} }} }} }}"""

_BREAKDOWN = """query($source: RankingSourceInput!, $id: ID!) {
  playerBreakdown(source: $source, playerId: $id) {
    engine unit role roleWar { name value } roleEra { name value } splits { name value } splitStat splitsExpected
    ledger { stage label delta side counted stat note } } }"""


def test_the_header_picks_the_engine(client):
    v2 = _gql(client, _ROWS)["rankedPlayers"]["rows"]
    legacy = _gql(client, _ROWS, engine="legacy")["rankedPlayers"]["rows"]
    assert {r["source"]["engine"] for r in v2} == {"v2"}
    assert {r["source"]["engine"] for r in legacy} == {"legacy"}
    assert all(r["preDemandRank"] for r in v2)
    assert all(r["preDemandScore"] is None for r in legacy)
    # an unknown engine falls back to the default
    junk = _gql(client, _ROWS, engine="v9")["rankedPlayers"]["rows"]
    assert {r["source"]["engine"] for r in junk} == {"v2"}


def test_breakdown_carries_the_ledger(client):
    top = _gql(client, _ROWS)["rankedPlayers"]["rows"][0]
    source = {"className": CLASS}
    b = _gql(client, _BREAKDOWN, source=source, id=top["id"])["playerBreakdown"]
    assert b["engine"] == "v2" and b["unit"] == "WAR points (50 + 10 x WAR)"
    counted = [line["delta"] for line in b["ledger"] if line["counted"]]
    assert sum(counted) == pytest.approx(top["modelScore"], abs=0.01)
    assert {line["stage"] for line in b["ledger"]} >= {"model", "modifiers", "demand"}
    # each line carries what it read apart from its name, and the role he's valued in
    assert b["role"]
    assert any(line["stat"] for line in b["ledger"] if line["stage"] == "model")
    if b["roleWar"]:
        assert {r["name"] for r in b["roleWar"]} == {"SP", "RP"}
        assert "RP" in {r["name"] for r in b["roleEra"]}
    # the source can name the engine itself, over the header
    b = _gql(client, _BREAKDOWN, source={**source, "engine": "legacy"}, id=top["id"])["playerBreakdown"]
    assert b["engine"] == "legacy" and b["ledger"] == [] and b["unit"] is None
    assert b["role"] is None and b["roleWar"] == [] and b["splits"] == []


def test_breakdown_carries_the_judged_sides_splits(client):
    # a draft class has no split ratings: a hitter shows the splits expected
    # for his batting hand, a pitcher the ones estimated from his hand, slot
    # and pitches
    source = {"className": CLASS}
    for row in _gql(client, _ROWS)["rankedPlayers"]["rows"]:
        b = _gql(client, _BREAKDOWN, source=source, id=row["id"])["playerBreakdown"]
        side = next(line["side"] for line in b["ledger"] if line["counted"] and line["side"])
        if side == "pitching":
            assert b["roleEra"]
            if b["splits"]:
                assert [s["name"] for s in b["splits"]] == ["vs LHB", "vs RHB"]
                assert b["splitStat"] == "ERA" and b["splitsExpected"]
        elif b["splits"]:
            assert [s["name"] for s in b["splits"]] == ["vs LHP", "vs RHP"]
            assert b["splitStat"] == "wRC+" and b["splitsExpected"]


_SIDES = f"""{{ rankedPlayers(name: "{CLASS}", allRows: true)
  {{ rows {{ type role preDemandScore positionPlayerScore battingScoreComponent fieldingScoreComponent
    runningScoreComponent pitcherScore starterComponent relieverComponent
    war battingWar fieldingWar runningWar starterWar relieverWar }} }} }}"""
_BATTING_SIDE = ("positionPlayerScore", "battingScoreComponent", "fieldingScoreComponent",
                 "runningScoreComponent", "battingWar", "fieldingWar", "runningWar")
_PITCHING_SIDE = ("pitcherScore", "starterComponent", "relieverComponent", "starterWar", "relieverWar")


@pytest.mark.parametrize("engine", ranking_engine.ENGINES)
def test_rows_carry_only_the_side_their_type_is_judged_on(client, engine):
    rows = _gql(client, _SIDES, engine=engine)["rankedPlayers"]["rows"]
    assert {r["type"] for r in rows} >= {"Hitter", "Pitcher"}
    for r in rows:
        if r["type"] == "Hitter":
            assert all(r[f] is None for f in _PITCHING_SIDE), r
        if r["type"] == "Pitcher":
            assert all(r[f] is None for f in _BATTING_SIDE), r
        if engine == "legacy":
            assert r["war"] is None and r["role"] is None
            continue
        # v2: his value in WAR before demand, its parts, and where he's valued
        assert r["war"] == pytest.approx((r["preDemandScore"] - 50) / 10, abs=0.01)
        if r["type"] == "Hitter":
            assert r["battingWar"] == pytest.approx(r["battingScoreComponent"] / 10, abs=0.01)
            assert r["role"] not in ("SP", "RP")
        if r["type"] == "Pitcher":
            assert r["role"] in ("SP", "RP")
            assert r["starterWar"] == pytest.approx(r["starterComponent"] / 10, abs=0.01)


def test_download_takes_the_engine_as_a_query_param(client):
    assert client.get(f"/download/{CLASS}/upload.csv?engine=legacy").status_code == 200


def test_v2_stores_the_modeled_line(data_dir):
    from league_snapshot import join_rows
    from models.game_players import GamePlayer
    from ranking import get_ranker
    from tests.test_league_snapshot import make_snapshot_csvs

    ranked = get_ranker("overall").rank([GamePlayer(dict(r)) for r in join_rows(*make_snapshot_csvs())])
    results_store.save_run(
        "league", "fx", "overall", 1, [results_store.result_from_scored(s) for s in ranked], engine="v2"
    )
    rows = {r["id"]: r for r in results_store.load_results("league", "fx", "overall", engine="v2")}
    hitters = [s for s in ranked if s.position not in ("SP", "RP", "CL")]
    pitchers = [s for s in ranked if s.position in ("SP", "RP", "CL")]
    assert hitters and all(rows[s.id]["wrc_plus"] == s.wrc_plus is not None for s in hitters)
    assert pitchers and all(0 < rows[s.id]["era"] == s.era for s in pitchers)


_COMPARE = """query($sort: RankedPlayerSort, $filter: RankedPlayerFilter) {
  rankedPlayers(name: "%s", sort: $sort, filter: $filter, pageSize: 200, compare: true) {
    totalRecords
    rows { id rank position legacyScore legacyRank v2Score v2Rank scoreDiff rankDiff }
  }
}""" % CLASS


def test_compare_view_lines_up_both_engines(client):
    page = _gql(client, _COMPARE)["rankedPlayers"]
    rows = page["rows"]
    assert page["totalRecords"] == len(rows) == 80
    # the table's own (v2) order, with each engine's ranks, both complete
    assert [r["v2Rank"] for r in rows] == [r["rank"] for r in rows] == list(range(1, 81))
    assert sorted(r["legacyRank"] for r in rows) == list(range(1, 81))
    for r in rows:
        assert r["rankDiff"] == r["legacyRank"] - r["v2Rank"]
        assert r["scoreDiff"] == pytest.approx(r["v2Score"] - r["legacyScore"])
    # the same top player the ranked table serves under the legacy engine
    top = _gql(client, _ROWS, engine="legacy")["rankedPlayers"]["rows"][0]["id"]
    assert top == next(r["id"] for r in rows if r["legacyRank"] == 1)


def test_compare_view_sorts_and_filters(client):
    risers = _gql(client, _COMPARE, sort={"field": "rankDiff", "order": -1})["rankedPlayers"]["rows"]
    diffs = [r["rankDiff"] for r in risers]
    assert diffs == sorted(diffs, reverse=True)
    pitchers = _gql(client, _COMPARE, filter={"positions": ["SP", "RP"]})["rankedPlayers"]["rows"]
    assert pitchers and {r["position"] for r in pitchers} <= {"SP", "RP"}
    big = _gql(client, _COMPARE, filter={"numeric": [{"field": "rankDiff", "min": 5}]})["rankedPlayers"]["rows"]
    assert all(r["rankDiff"] >= 5 for r in big)


def test_rows_carry_no_comparison_unless_asked(client):
    rows = _gql(client, f"""{{ rankedPlayers(name: "{CLASS}", pageSize: 3) {{ rows {{ v2Rank rankDiff }} }} }}""")
    assert all(r == {"v2Rank": None, "rankDiff": None} for r in rows["rankedPlayers"]["rows"])


def test_a_run_scored_by_another_model_is_rescored_on_its_next_read(fixture_class, monkeypatch):
    import pipeline
    from ranking import manifest

    pipeline.process_class(fixture_class)
    before = results_store.run_info("class", CLASS, "draft_class", "v2")
    assert results_store.class_results(fixture_class, engine="v2") is not None
    # a deploy that changes the model: both engines' runs are now stale, but
    # the class still counts as processed and is re-scored when read
    monkeypatch.setattr(manifest, "model_version", lambda: "next-model")
    assert results_store.class_results(fixture_class, engine="v2") is None
    rows = pipeline.class_results(fixture_class)
    assert rows
    after = results_store.run_info("class", CLASS, "draft_class", "v2")
    assert after["manifest"]["model_version"] == "next-model" != before["manifest"]["model_version"]
