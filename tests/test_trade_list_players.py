"""service.trade_list_players against a fixture snapshot: a live hit keeps model
scores, a player dropped from the snapshot renders stale from the denormalized
entry fields, and rows come back priority-then-score ordered."""
import csv
import io

import pytest

import league_snapshot
from league_snapshot import LeagueSnapshotContext, build_snapshot
from web import leagues, service
from tests.test_league_snapshot import (
    PLAYERS_HEADER,
    RATINGS_HEADER,
    TEAMS_CSV,
    _csv,
    _players_row,
    _ratings_row,
    make_snapshot_csvs,
)


def _build(league_id, ratings, players, teams=TEAMS_CSV):
    build_snapshot(LeagueSnapshotContext(league_id), ratings, players, teams)
    service._evict_league_payload_cache(league_id)


@pytest.fixture
def league(data_dir):
    lg = leagues.create_league("YFMLB", "yfmlb")
    _build(lg["id"], *make_snapshot_csvs())
    return lg["id"]


def test_missing_list_is_not_found(league):
    with pytest.raises(service.NotFound):
        service.trade_list_players(league, "ghost")


def test_live_hit_stale_miss_and_ordering(league):
    lst = service.create_trade_list(league, "SP targets")["id"]
    service.add_to_trade_list(league, lst, "100", priority="HIGH", note="ace")
    service.add_to_trade_list(league, lst, "200", priority="LOW")

    # the denormalized identity is captured at add-time from the snapshot
    entry_200 = next(
        e
        for e in service.trade_lists.get_list(league, lst)["entries"]
        if e["playerId"] == "200"
    )
    assert entry_200["name"] == "Big Bat"
    assert entry_200["position"] == "RF"
    assert entry_200["org"]

    # rebuild the snapshot without player 200, then add a target that was never
    # in the snapshot at all
    pitcher = _ratings_row(
        ID="100", Name="Ace Hurler", Pos="SP", Team="46", Org="46",
        Stf="60", Mov="55", Ctrl="50", Ovr="60", Pot="65",
    )
    _build(
        league,
        _csv(RATINGS_HEADER, [pitcher]),
        _csv(PLAYERS_HEADER, [_players_row(ID="100", Level="1",
             **{"Team ID": "46", "Parent Team ID": "46", "Organization ID": "46"})]),
    )
    service.add_to_trade_list(league, lst, "999", priority="MEDIUM")

    page = service.trade_list_players(league, lst)
    rows = {r["id"]: r for r in page["rows"]}
    assert page["total_records"] == 3

    # priority asc (HIGH, MEDIUM, LOW), score desc within a tier
    assert [r["id"] for r in page["rows"]] == ["100", "999", "200"]

    live = rows["100"]
    assert live["stale"] is False
    assert live["note"] == "ace" and live["priority"] == "HIGH"
    assert live["model_score"] is not None
    assert live["ratings"]

    dropped = rows["200"]
    assert dropped["stale"] is True
    assert dropped["priority"] == "LOW"
    assert dropped["name"] == "Big Bat" and dropped["position"] == "RF"
    assert dropped["org"]
    assert dropped["model_score"] is None

    never = rows["999"]
    assert never["stale"] is True
    assert never["name"] == "Player 999"


def test_no_snapshot_yields_all_stale(data_dir):
    lg = leagues.create_league("Fresh", "yfmlb")["id"]
    lst = service.create_trade_list(lg, "targets")["id"]
    service.add_to_trade_list(lg, lst, "42", priority="HIGH")
    page = service.trade_list_players(lg, lst)
    assert page["total_records"] == 1
    assert page["rows"][0]["stale"] is True
    assert page["rows"][0]["priority"] == "HIGH"
