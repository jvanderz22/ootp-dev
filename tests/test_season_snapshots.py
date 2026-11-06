"""web.service.collect_season_snapshots: one ratings snapshot per league per
season, taken when the app wakes up."""
import pytest

import league_snapshot
from tests.test_league_snapshot import make_snapshot_csvs
from web import leagues, service


@pytest.fixture
def league(data_dir, monkeypatch):
    lg = leagues.create_league(
        name="yfmlb", league_url="https://statsplus.net/yfmlb/", sessionid="s", csrftoken="t"
    )
    started = []
    monkeypatch.setattr(service, "start_league_refresh", lambda league_id: started.append(league_id))
    ctx = league_snapshot.LeagueSnapshotContext(lg["id"])
    return lg, ctx, started


def _game_date(monkeypatch, date):
    monkeypatch.setattr(service, "fetch_league_date", lambda url, cookie: date)


def test_archives_a_qualifying_stored_snapshot_without_refreshing(league, monkeypatch):
    lg, ctx, started = league
    league_snapshot.build_snapshot(ctx, *make_snapshot_csvs(), league_date="2042-03-01")
    league_snapshot.touch_checked(ctx, "2042-04-20")   # stored snapshot now dated past 4/8
    _game_date(monkeypatch, "2042-04-20")
    service.collect_season_snapshots()
    assert ctx.has_season_snapshot(2042)
    assert started == []


def test_refreshes_once_the_season_start_has_passed(league, monkeypatch):
    lg, ctx, started = league
    league_snapshot.build_snapshot(ctx, *make_snapshot_csvs(), league_date="2042-03-01")
    _game_date(monkeypatch, "2042-04-12")
    service.collect_season_snapshots()
    assert started == [lg["id"]]


@pytest.mark.parametrize("game_date", ["2042-03-15", "2042-09-01"])
def test_nothing_to_do_before_the_start_or_once_taken(league, monkeypatch, game_date):
    lg, ctx, started = league
    league_snapshot.build_snapshot(ctx, *make_snapshot_csvs(), league_date="2042-04-10")
    _game_date(monkeypatch, game_date)
    service.collect_season_snapshots()
    assert started == []


def test_league_without_a_login_is_skipped(data_dir, monkeypatch):
    lg = leagues.create_league(name="nolog", league_url="https://statsplus.net/x/")
    monkeypatch.setattr(service, "fetch_league_date", lambda *a: pytest.fail("no login"))
    assert service.collect_season_snapshots() == {lg["id"]: ["no StatsPlus login"]}
