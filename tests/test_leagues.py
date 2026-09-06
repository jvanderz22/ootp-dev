"""Unit coverage for web/leagues.py: storage, the class<->league mapping, the
single-league fallback, and the one-time migration from the old app-wide
web_config.json league URL."""
import json

import pytest

from web import leagues


def _make_class(data_dir, name, config=None):
    (data_dir / "datasets").mkdir(parents=True, exist_ok=True)
    (data_dir / "datasets" / f"{name}.csv").write_text("ID,POS,Name\n1,SS,Test\n")
    cdir = data_dir / "processed_classes" / name
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "config.json").write_text(json.dumps(config or {"ranking_method": "draft_class"}))


def test_create_list_and_assign(data_dir):
    _make_class(data_dir, "alpha")
    _make_class(data_dir, "beta")

    lg = leagues.create_league("My League", "yfmlb", 7, ["alpha"])
    other = leagues.create_league("Other", "wbf")
    assert lg["id"] == "my-league"
    assert lg["league_url"] == "https://statsplus.net/yfmlb/"
    assert lg["default_lid"] == 7

    # two leagues -> no single-league fallback; only the explicit pin counts
    assert leagues.class_names_for_league("my-league") == ["alpha"]
    assert leagues.class_names_for_league(other["id"]) == []
    assert leagues.explicit_class_league_id("alpha") == "my-league"
    assert leagues.explicit_class_league_id("beta") is None
    assert leagues.league_for_class("alpha")["id"] == "my-league"
    assert leagues.league_for_class("beta") is None


def test_single_league_fallback(data_dir):
    _make_class(data_dir, "alpha")
    leagues.create_league("Only", "yfmlb")
    # class has no explicit league_id, but there is exactly one league
    assert leagues.explicit_class_league_id("alpha") is None
    assert leagues.league_for_class("alpha")["id"] == "only"
    # ...but listing is explicit-only: an unpinned class is "unmapped"
    assert leagues.class_names_for_league("only") == []


def test_slug_dedupe(data_dir):
    a = leagues.create_league("League")
    b = leagues.create_league("League")
    assert {a["id"], b["id"]} == {"league", "league-2"}


def test_update_reassigns_and_delete_unassigns(data_dir):
    _make_class(data_dir, "alpha")
    _make_class(data_dir, "beta")
    lg = leagues.create_league("L", "yfmlb", class_names=["alpha"])

    leagues.update_league(lg["id"], class_names=["beta"])
    assert leagues.explicit_class_league_id("alpha") is None
    assert leagues.explicit_class_league_id("beta") == lg["id"]

    leagues.delete_league(lg["id"])
    assert leagues.load_leagues() == []
    assert leagues.explicit_class_league_id("beta") is None


def test_reject_foreign_host(data_dir):
    from statsplus_api import StatsPlusError

    with pytest.raises(StatsPlusError):
        leagues.create_league("bad", "https://evil.example/x")


def test_migrates_legacy_web_config(data_dir):
    (data_dir / "web_config.json").write_text(
        json.dumps({"league_url": "https://statsplus.net/yfmlb/", "default_lid": 3,
                    "sessionid": "s", "csrftoken": "c"})
    )
    migrated = leagues.load_leagues()
    assert len(migrated) == 1
    assert migrated[0]["name"] == "yfmlb"
    assert migrated[0]["league_url"] == "https://statsplus.net/yfmlb/"
    assert migrated[0]["default_lid"] == 3
    # the old app-wide cookie is folded into the seeded league
    assert migrated[0]["sessionid"] == "s"
    assert migrated[0]["csrftoken"] == "c"
    # persisted, so a second load is a plain read
    assert (data_dir / "leagues.json").exists()
    assert leagues.load_leagues() == migrated


def test_seeds_legacy_cookie_into_existing_leagues(data_dir):
    """An install that already has leagues.json but predates per-league cookies:
    the old app-wide cookie is folded into every cookie-less league, once."""
    (data_dir / "leagues.json").write_text(
        json.dumps({"leagues": [{"id": "a", "name": "A", "league_url": "x"}]})
    )
    (data_dir / "web_config.json").write_text(
        json.dumps({"sessionid": "leg-s", "csrftoken": "leg-c"})
    )
    seeded = leagues.load_leagues()
    assert seeded[0]["sessionid"] == "leg-s" and seeded[0]["csrftoken"] == "leg-c"

    stored = json.loads((data_dir / "leagues.json").read_text())
    assert stored["cookies_seeded"] is True
    # a later web_config change is ignored - seeding only runs once
    (data_dir / "web_config.json").write_text(json.dumps({"sessionid": "new"}))
    assert leagues.load_leagues()[0]["sessionid"] == "leg-s"


def test_per_league_cookie_crud_and_public_projection(data_dir):
    from web.settings import cookie_header

    lg = leagues.create_league("Ck", "yfmlb", sessionid="  aa ", csrftoken="csrftoken=bb")
    assert lg["sessionid"] == "aa" and lg["csrftoken"] == "bb"
    assert cookie_header(lg) == "sessionid=aa; csrftoken=bb"

    # public projection hides the values, exposes booleans only
    pub = leagues.public_league(leagues.get_league(lg["id"]))
    assert "sessionid" not in pub and "csrftoken" not in pub
    assert pub["has_sessionid"] is True and pub["has_csrftoken"] is True

    # blank keeps, non-blank replaces
    leagues.update_league(lg["id"], sessionid="", csrftoken="cc")
    stored = leagues.get_league(lg["id"])
    assert stored["sessionid"] == "aa" and stored["csrftoken"] == "cc"


def test_no_legacy_config_yields_empty(data_dir):
    assert leagues.load_leagues() == []
