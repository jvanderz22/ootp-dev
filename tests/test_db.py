"""The SQLite layer: migrations, transactions, the one-time legacy-file import,
and the state that moved into the database (refresh jobs, league deletion)."""
import json
import threading

import pytest

import db


def test_migration_runs_once_and_import_is_one_time(data_dir):
    db.connect()
    assert db.query_one("PRAGMA user_version")[0] == len(db._MIGRATIONS)
    imported = db.query_one("SELECT value FROM app_meta WHERE key = 'files_imported_at'")
    assert imported is not None

    # files that appear after the import are never picked up
    (data_dir / "leagues.json").write_text(
        json.dumps({"leagues": [{"id": "late", "name": "Late"}], "cookies_seeded": True})
    )
    db.close_all()
    assert db.query("SELECT id FROM leagues") == []


def test_transaction_rolls_back_and_nests(data_dir):
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO app_meta (key, value) VALUES ('a', '1')")
            with db.transaction() as inner:  # joins the outer transaction
                inner.execute("INSERT INTO app_meta (key, value) VALUES ('b', '2')")
            raise RuntimeError("boom")
    assert db.query("SELECT key FROM app_meta WHERE key IN ('a', 'b')") == []

    with db.transaction() as conn:
        conn.execute("INSERT INTO app_meta (key, value) VALUES ('a', '1')")
        with db.transaction() as inner:
            inner.execute("INSERT INTO app_meta (key, value) VALUES ('b', '2')")
    assert {r["key"] for r in db.query("SELECT key FROM app_meta WHERE key IN ('a', 'b')")} == {"a", "b"}


def test_each_thread_gets_its_own_connection(data_dir):
    mine = db.connect()
    theirs = []
    t = threading.Thread(target=lambda: theirs.append(db.connect()))
    t.start()
    t.join()
    assert theirs[0] is not mine
    assert db.connect() is mine


def test_import_tolerates_dangling_references(data_dir):
    """A class pinned to a deleted league imports as unassigned, a snapshot for
    a league that no longer exists is skipped, and a custom order / drafted
    file comes along with its class."""
    (data_dir / "leagues.json").write_text(json.dumps({
        "leagues": [{"id": "live", "name": "Live", "league_url": "https://statsplus.net/live/"}],
        "cookies_seeded": True,
    }))
    for name, league in (("pinned", "live"), ("orphan", "gone")):
        (data_dir / "datasets").mkdir(exist_ok=True)
        (data_dir / "datasets" / f"{name}.csv").write_text("ID,POS,Name\n1,SS,Ann Lee\n2,SP,Bo Diaz\n")
        folder = data_dir / "processed_classes" / name
        folder.mkdir(parents=True)
        (folder / "config.json").write_text(json.dumps({"ranking_method": "overall", "league_id": league}))
    (data_dir / "processed_classes" / "pinned" / "custom_ranking.json").write_text(
        json.dumps({"order": [2, 1], "updated_at": 1})
    )
    (data_dir / "processed_classes" / "pinned" / "drafted_players.csv").write_text(
        "id,name,position,round,pick,overall,team\n2,Bo Diaz,SP,1,3,3,Expos\n"
    )
    (data_dir / "processed_classes" / "orphan" / "drafted_players.csv").write_text(
        "Round,Pick,Overall,Team,Selection,Time\n2,1,31,Expos,SS Ann Lee,\n"
    )
    for lid in ("live", "gone"):
        (data_dir / "league_snapshots" / lid).mkdir(parents=True)
        (data_dir / "league_snapshots" / lid / "meta.json").write_text(
            json.dumps({"fetched_at": "2042-01-01T00:00:00+00:00", "player_count": 5})
        )

    from context import DraftClassContext
    from custom_ranking import load_order
    from drafted_players import get_drafted_players_info
    from web import leagues

    assert leagues.explicit_class_league_id("pinned") == "live"
    assert leagues.explicit_class_league_id("orphan") is None
    assert DraftClassContext("orphan").ranking_method == "overall"
    assert load_order(DraftClassContext("pinned")) == ["2", "1"]
    assert get_drafted_players_info(DraftClassContext("pinned"))["2"]["team"] == "Expos"
    # the legacy scrape row is resolved to an id by name + position
    assert get_drafted_players_info(DraftClassContext("orphan"))["1"]["round"] == "2"
    assert [r["league_id"] for r in db.query("SELECT league_id FROM league_snapshots")] == ["live"]


def test_corrupt_leagues_json_falls_back_to_legacy_config(data_dir):
    (data_dir / "leagues.json").write_text("{not json")
    (data_dir / "web_config.json").write_text(json.dumps({"league_url": "https://statsplus.net/yfmlb/"}))
    from web import leagues

    assert [lg["id"] for lg in leagues.load_leagues()] == ["yfmlb"]


def test_running_job_without_a_worker_reads_as_interrupted(data_dir):
    """The machine stopped mid-refresh: the row still says running, but this
    process has no worker thread for it."""
    from web import leagues, service

    lid = leagues.create_league("Halted", "https://statsplus.net/halted/")["id"]
    service._save_job(lid, state="running", started_at=service._now_iso(), progress="Scoring…")
    status = service.league_refresh_status(lid)
    assert status["state"] == "error"
    assert "interrupted" in status["error"]
    assert status["progress"] is None


def test_delete_league_cascades(data_dir):
    from context import DraftClassContext
    from league_snapshot import LeagueSnapshotContext, build_snapshot
    from tests.test_league_snapshot import make_snapshot_csvs
    from web import leagues, service

    lid = leagues.create_league("Gone Soon", "https://statsplus.net/gone/")["id"]
    ctx = LeagueSnapshotContext(lid)
    build_snapshot(ctx, *make_snapshot_csvs())
    service._save_job(lid, state="done")
    DraftClassContext("c").register()
    leagues.set_class_league("c", lid)

    service.delete_league(lid)
    assert ctx.load_meta() == {}
    assert not ctx.snapshot_dir.exists()
    assert db.query("SELECT * FROM refresh_jobs") == []
    assert leagues.explicit_class_league_id("c") is None
