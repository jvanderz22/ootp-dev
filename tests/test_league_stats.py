"""league_stats.py: storing StatsPlus season stats per league."""
import csv

import pytest

import league_stats
import statsplus_api

LEAGUE = {"id": "yfmlb", "league_url": "https://statsplus.net/yfmlb/"}
LGDATA = {"leagues": [
    {"league_id": 162, "level": 4},
    {"league_id": 153, "level": 1},
    {"league_id": 154, "level": 2},
]}


@pytest.fixture
def api(monkeypatch):
    """Fake StatsPlus: one row per (kind, year, lid), nothing for 2043."""
    calls = []
    monkeypatch.setattr(league_stats, "REQUEST_PAUSE", 0)
    monkeypatch.setattr(statsplus_api, "fetch_league_date", lambda url, ck: "2042-11-07")
    monkeypatch.setattr(statsplus_api, "fetch_league_data", lambda url, ck: LGDATA)

    def fetch(url, ck, kind, year, lid=None):
        calls.append((kind, year, lid))
        if year == 2043:
            return ""
        extra = ",war" if kind != "field" else ""
        val = ",1.5" if kind != "field" else ""
        return f"player_id,year,league_id{extra}\n{lid}0,{year},{lid}{val}\n"

    monkeypatch.setattr(statsplus_api, "fetch_player_stats", fetch)
    return calls


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_pull_stores_every_level_majors_first(data_dir, api):
    league_stats.pull(LEAGUE, [2041], kinds=("bat",), cookie="x", log=lambda m: None)
    rows = _rows(league_stats.stats_file("yfmlb", "bat", 2041))
    assert [r["league_id"] for r in rows] == ["153", "154", "162"]
    assert rows[0]["war"] == "1.5"


def test_past_seasons_skip_but_the_current_one_refetches(data_dir, api):
    quiet = {"cookie": "x", "log": lambda m: None, "kinds": ("pitch",)}
    league_stats.pull(LEAGUE, [2041, 2042], **quiet)
    api.clear()
    league_stats.pull(LEAGUE, [2041, 2042], **quiet)
    assert {year for _, year, _ in api} == {2042}
    api.clear()
    league_stats.pull(LEAGUE, [2041], refetch=True, **quiet)
    assert {year for _, year, _ in api} == {2041}


def test_empty_season_is_not_written(data_dir, api):
    written = league_stats.pull(LEAGUE, [2043], cookie="x", log=lambda m: None)
    assert written == []
    assert not league_stats.stats_dir("yfmlb").exists()


def test_years_spec():
    assert list(league_stats._years("2042")) == [2042]
    assert list(league_stats._years("2039-2042")) == [2039, 2040, 2041, 2042]
