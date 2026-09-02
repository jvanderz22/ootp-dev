import pytest

from context import DraftClassContext
from drafted_players import get_drafted_player_ids, get_drafted_players_info
import pytest as _pytest

from statsplus_api import (
    StatsPlusAuthError,
    StatsPlusError,
    _parse_draft_csv,
    fetch_draft_picks,
    normalize_league_url,
    write_drafted_players_file,
)


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
