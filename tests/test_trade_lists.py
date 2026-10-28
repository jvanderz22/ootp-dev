"""Unit coverage for web/trade_lists.py: table CRUD, slug uniqueness, priority
validation, entry upsert, the league-delete cascade, and the trade_lists.json
import an upgraded install runs."""
import json

import pytest

import db
from web import leagues
from web import trade_lists as tl


@pytest.fixture(autouse=True)
def _leagues(data_dir):
    # lists belong to a league row (foreign key)
    for name in ("lg", "keep", "other"):
        leagues.create_league(name)


def test_create_list_slugs_and_dedupes(data_dir):
    a = tl.create_list("lg", "SP Targets")
    b = tl.create_list("lg", "SP Targets")
    assert a["id"] == "sp-targets"
    assert b["id"] == "sp-targets-2"
    assert a["entries"] == []
    assert [x["id"] for x in tl.lists_for_league("lg")] == ["sp-targets", "sp-targets-2"]
    # keyed by league - a different league is its own namespace
    assert tl.lists_for_league("other") == []


def test_create_list_requires_name(data_dir):
    with pytest.raises(ValueError):
        tl.create_list("lg", "   ")


def test_rename_keeps_id(data_dir):
    lst = tl.create_list("lg", "Sell high")
    renamed = tl.rename_list("lg", lst["id"], "2027 deadline")
    assert renamed["id"] == lst["id"] == "sell-high"
    assert renamed["name"] == "2027 deadline"
    assert tl.get_list("lg", "sell-high")["name"] == "2027 deadline"


def test_delete_list(data_dir):
    tl.create_list("lg", "A")
    tl.create_list("lg", "B")
    tl.delete_list("lg", "a")
    assert [x["id"] for x in tl.lists_for_league("lg")] == ["b"]
    with pytest.raises(ValueError):
        tl.delete_list("lg", "a")


def test_add_entry_upserts_by_player_id(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "123", priority="HIGH", note="give up Keller",
                 denorm={"name": "Joe Arm", "position": "SP", "org": "Rockies"})
    tl.add_entry("lg", "l", "456", priority="LOW")
    lst = tl.get_list("lg", "l")
    assert [e["playerId"] for e in lst["entries"]] == ["123", "456"]
    first = lst["entries"][0]
    assert first["priority"] == "HIGH"
    assert first["note"] == "give up Keller"
    assert first["name"] == "Joe Arm" and first["position"] == "SP" and first["org"] == "Rockies"
    added_at = first["addedAt"]

    # re-adding 123 patches in place, keeps addedAt, does not duplicate
    tl.add_entry("lg", "l", "123", priority="MEDIUM")
    lst = tl.get_list("lg", "l")
    assert len(lst["entries"]) == 2
    assert lst["entries"][0]["priority"] == "MEDIUM"
    assert lst["entries"][0]["note"] == "give up Keller"  # untouched when note is None
    assert lst["entries"][0]["addedAt"] == added_at


def test_add_entry_defaults_priority_to_medium(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "1")
    assert tl.get_list("lg", "l")["entries"][0]["priority"] == "MEDIUM"


def test_priority_validation(data_dir):
    tl.create_list("lg", "L")
    with pytest.raises(ValueError):
        tl.add_entry("lg", "l", "1", priority="URGENT")
    tl.add_entry("lg", "l", "1", priority="HIGH")
    with pytest.raises(ValueError):
        tl.set_entry("lg", "l", "1", priority="nope")
    # case-insensitive on the way in
    tl.add_entry("lg", "l", "2", priority="low")
    assert tl.get_list("lg", "l")["entries"][1]["priority"] == "LOW"


def test_set_entry_patches_and_clears(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "1", priority="HIGH", note="original")
    tl.set_entry("lg", "l", "1", note="")
    assert tl.get_list("lg", "l")["entries"][0]["note"] == ""
    assert tl.get_list("lg", "l")["entries"][0]["priority"] == "HIGH"  # None leaves it
    tl.set_entry("lg", "l", "1", priority="LOW")
    assert tl.get_list("lg", "l")["entries"][0]["priority"] == "LOW"
    with pytest.raises(ValueError):
        tl.set_entry("lg", "l", "999", priority="LOW")


def test_remove_entry(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "1")
    tl.add_entry("lg", "l", "2")
    tl.remove_entry("lg", "l", "1")
    assert [e["playerId"] for e in tl.get_list("lg", "l")["entries"]] == ["2"]
    with pytest.raises(ValueError):
        tl.remove_entry("lg", "l", "1")


def test_entry_ops_on_missing_list_raise(data_dir):
    with pytest.raises(ValueError):
        tl.add_entry("lg", "ghost", "1")
    with pytest.raises(ValueError):
        tl.rename_list("lg", "ghost", "x")


def test_priority_rank_ordering(data_dir):
    assert tl.priority_rank("HIGH") < tl.priority_rank("MEDIUM") < tl.priority_rank("LOW")
    assert tl.priority_rank(None) > tl.priority_rank("LOW")


def test_deleting_the_league_drops_its_lists(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "1")
    tl.create_list("keep", "K")
    leagues.delete_league("lg")
    assert tl.lists_for_league("lg") == []
    assert db.query("SELECT * FROM trade_list_entries WHERE league_id = 'lg'") == []
    assert [x["id"] for x in tl.lists_for_league("keep")] == ["k"]


def test_persists_across_reconnect(data_dir):
    tl.create_list("lg", "L")
    tl.add_entry("lg", "l", "1", priority="HIGH")
    db.close_all()
    assert tl.get_list("lg", "l")["entries"][0]["playerId"] == "1"


def test_nothing_stored_reads_empty(data_dir):
    assert tl.lists_for_league("lg") == []
    assert tl.get_list("lg", "x") is None


def test_upgrade_imports_trade_lists_json(data_dir, monkeypatch):
    """Production's path: a version-1 database (already holding the leagues)
    plus the old trade_lists.json, opened by code with migration 2."""
    db.close_all()
    (data_dir / "app.db").unlink()
    for suffix in ("-wal", "-shm"):
        (data_dir / f"app.db{suffix}").unlink(missing_ok=True)
    with monkeypatch.context() as m:
        m.setattr(db, "_MIGRATIONS", db._MIGRATIONS[:1])
        leagues.create_league("lg")
        assert db.query_one("PRAGMA user_version")[0] == 1
        db.close_all()

    (data_dir / "trade_lists.json").write_text(json.dumps({
        "lg": [
            {"id": "a", "name": "A", "createdAt": "2026-09-08T01:12:44Z", "entries": [
                {"playerId": "2", "priority": "LOW", "note": "n", "addedAt": "t1",
                 "name": "Two", "position": "SP", "org": "X"},
                {"playerId": "1", "priority": "HIGH", "note": "", "addedAt": "t2",
                 "name": "One", "position": "C", "org": ""},
                {"playerId": "2", "priority": "HIGH", "note": "dupe"},
            ]},
            {"id": "b", "name": "B", "createdAt": None, "entries": []},
        ],
        "gone": [{"id": "x", "name": "X", "entries": [{"playerId": "9"}]}],
    }))
    assert db.query_one("PRAGMA user_version")[0] == len(db._MIGRATIONS)
    assert tl.lists_for_league("lg") == [
        {"id": "a", "name": "A", "createdAt": "2026-09-08T01:12:44Z", "entries": [
            {"playerId": "2", "priority": "LOW", "note": "n", "addedAt": "t1",
             "name": "Two", "position": "SP", "org": "X"},
            {"playerId": "1", "priority": "HIGH", "note": "", "addedAt": "t2",
             "name": "One", "position": "C", "org": ""},
        ]},
        {"id": "b", "name": "B", "createdAt": None, "entries": []},
    ]
    # a league that no longer exists brings nothing in
    assert db.query("SELECT * FROM trade_lists WHERE league_id = 'gone'") == []
    # the file is left in place, like every other imported file
    assert (data_dir / "trade_lists.json").exists()
