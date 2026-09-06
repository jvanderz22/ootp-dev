import pytest

from context import DraftClassContext
from drafted_players import get_drafted_player_ids, get_drafted_players_info
import pytest as _pytest

import statsplus_api
from statsplus_api import (
    StatsPlusAuthError,
    StatsPlusError,
    _api_url,
    _canonical_league_url,
    _draft_url,
    _parse_draft_csv,
    fetch_draft_picks,
    fetch_league_date,
    normalize_league_url,
    poll_ratings_export,
    start_ratings_job,
    write_drafted_players_file,
)


class _FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def _stub_get(monkeypatch, *responses):
    """Patch httpx.get to hand back `responses` in order (last one repeats)."""
    import httpx

    seq = list(responses)

    def fake_get(*_a, **_k):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr(httpx, "get", fake_get)


def test_fetch_league_date(monkeypatch):
    _stub_get(monkeypatch, _FakeResp("2042-05-19\n"))
    assert fetch_league_date("yfmlb", "sessionid=x; csrftoken=y") == "2042-05-19"


def test_start_ratings_job_parses_poll_url(monkeypatch):
    uuid = "3de70b01-337b-4baf-a948-f18831706dc4"
    _stub_get(
        monkeypatch,
        _FakeResp(f"queued; poll https://statsplus.net/yfmlb/api/mycsv/?request={uuid}"),
    )
    assert start_ratings_job("yfmlb", "c").endswith(f"request={uuid}")


def test_start_ratings_job_without_poll_url_raises(monkeypatch):
    _stub_get(monkeypatch, _FakeResp("Request too soon, wait 284 seconds"))
    with pytest.raises(StatsPlusError):
        start_ratings_job("yfmlb", "c")


def test_poll_ratings_export_waits_then_returns_csv(monkeypatch):
    _stub_get(
        monkeypatch,
        _FakeResp("...still in progress..."),
        _FakeResp("ID,Name\n1,Bob\n"),
    )
    out = poll_ratings_export(
        "https://statsplus.net/yfmlb/api/mycsv/?request=abc", "c",
        interval=0, _sleep=lambda _s: None,
    )
    assert out.startswith("ID,Name")


def test_poll_ratings_export_times_out(monkeypatch):
    _stub_get(monkeypatch, _FakeResp("still in progress"))
    with pytest.raises(StatsPlusError):
        poll_ratings_export("https://x/api/mycsv/?request=abc", "c",
                            timeout=0, interval=0, _sleep=lambda _s: None)


@_pytest.mark.parametrize(
    "raw,expected",
    [
        ("yfmlb", "https://statsplus.net/yfmlb/"),
        ("https://statsplus.net/yfmlb/", "https://statsplus.net/yfmlb/"),
        ("statsplus.net/yfmlb", "https://statsplus.net/yfmlb/"),
        ("http://statsplus.net/yfmlb", "https://statsplus.net/yfmlb/"),
        ("atl-01.statsplus.net/wbf/", "https://atl-01.statsplus.net/wbf/"),
        ("", ""),
    ],
)
def test_normalize_league_url(raw, expected):
    assert normalize_league_url(raw) == expected


def test_normalize_league_url_rejects_other_hosts():
    with _pytest.raises(StatsPlusError):
        normalize_league_url("https://example.com/yfmlb")


@_pytest.mark.parametrize(
    "raw",
    [
        "https://atl-01.statsplus.net/wbf/",
        "atl-01.statsplus.net/wbf",
        "https://statsplus.net/wbf/",
        "wbf",
    ],
)
def test_api_calls_target_the_apex_host(raw):
    # A per-node subdomain reaches the game server, which has no StatsPlus
    # session - every /api/ request must go to statsplus.net/<slug>/.
    assert _canonical_league_url(raw) == "https://statsplus.net/wbf/"
    assert _api_url(raw, "ratings") == "https://statsplus.net/wbf/api/ratings/"
    assert _draft_url(raw) == "https://statsplus.net/wbf/api/draftv2/"


def test_login_notice_body_is_an_auth_error(monkeypatch):
    _stub_get(
        monkeypatch,
        _FakeResp(
            "This API requires user to be logged in, visit "
            "https://statsplus.net/wbf/ and log in to a linked team"
        ),
    )
    with pytest.raises(StatsPlusAuthError):
        fetch_league_date("https://atl-01.statsplus.net/wbf/", "sessionid=x")


def test_start_ratings_job_login_notice_is_an_auth_error(monkeypatch):
    _stub_get(
        monkeypatch,
        _FakeResp("This API requires user to be logged in, visit ... linked team"),
    )
    with pytest.raises(StatsPlusAuthError):
        start_ratings_job("wbf", "c")

DRAFTV2_CSV = (
    "ID,Round,Pick In Round,Supp,Overall,Player Name,Team,Team ID,Position,Age,College,Auto Pick,Time (UTC)\n"
    "76230,1,1,,1,Pat Calhoon,Expos,5,SP,22,,No,2026-01-01 00:00:00\n"
    "999999,1,2,,2,Nobody Here,Yanks,3,SS,19,State U,Yes,2026-01-01 00:01:00\n"
)


def test_parse_draftv2_csv():
    picks = _parse_draft_csv(DRAFTV2_CSV)
    assert [p.id for p in picks] == ["76230", "999999"]
    assert picks[0].name == "Pat Calhoon"
    assert picks[0].position == "SP"
    assert picks[0].team == "Expos"


def test_fetch_requires_cookie():
    with pytest.raises(StatsPlusAuthError):
        fetch_draft_picks("yfmlb", cookie="")


def test_write_and_read_exact_id_match(sample_class):
    ctx = DraftClassContext(sample_class)
    write_drafted_players_file(ctx, _parse_draft_csv(DRAFTV2_CSV))

    info = get_drafted_players_info(ctx)
    assert "76230" in info                       # id present in the dataset
    assert info["76230"]["team"] == "Expos"
    assert get_drafted_player_ids(ctx) == {"76230", "999999"}


def test_legacy_selection_format_still_reads(sample_class):
    ctx = DraftClassContext(sample_class)
    ctx.drafted_players_file.write_text(
        "Round,Pick,Overall,Team,Selection,Time\n1,1,1,Montreal,SP Pat Calhoon,\n"
    )
    ids = get_drafted_player_ids(ctx)
    assert "76230" in ids  # matched by name+position against the dataset
