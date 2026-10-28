"""SQLite storage for the web app and the CLI: one database at $DATA_DIR/app.db.

The app runs as a single process on one machine with one volume, so SQLite in
WAL mode is the whole datastore - no server. Connections are per thread (the web
layer works on anyio worker threads plus the league-refresh daemon thread) and
per database path (tests point DATA_DIR at a fresh directory each time).

Writes go through `transaction()`; reads can use `query` / `query_one` directly.
The schema is versioned with `PRAGMA user_version`; the first connection to a
database runs any pending migrations. Migrations 1 and 2 also import the files a
pre-SQLite install left under $DATA_DIR (see `db_import.py`).
"""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_FILENAME = "app.db"

_SCHEMA_V1 = """
CREATE TABLE app_meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE leagues (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  league_url TEXT NOT NULL DEFAULT '',
  default_lid INTEGER,
  sessionid TEXT NOT NULL DEFAULT '',
  csrftoken TEXT NOT NULL DEFAULT '',
  game_league_ids TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE draft_classes (
  name TEXT PRIMARY KEY,
  ranking_method TEXT NOT NULL DEFAULT 'draft_class',
  print_method TEXT NOT NULL DEFAULT 'draft_prospects',
  league_id TEXT REFERENCES leagues(id) ON DELETE SET NULL,
  custom_order TEXT,
  data_version INTEGER NOT NULL DEFAULT 1,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE drafted_picks (
  class_name TEXT NOT NULL REFERENCES draft_classes(name) ON DELETE CASCADE,
  player_id TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  round TEXT NOT NULL DEFAULT '',
  round_pick TEXT NOT NULL DEFAULT '',
  overall_pick TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (class_name, player_id)
);

CREATE TABLE league_snapshots (
  league_id TEXT PRIMARY KEY REFERENCES leagues(id) ON DELETE CASCADE,
  version INTEGER NOT NULL DEFAULT 1,
  fetched_at TEXT,
  last_checked_at TEXT,
  league_date TEXT,
  player_count INTEGER,
  total_row_count INTEGER
);

CREATE TABLE refresh_jobs (
  league_id TEXT PRIMARY KEY REFERENCES leagues(id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  progress TEXT
);

CREATE TABLE model_runs (
  scope TEXT NOT NULL CHECK (scope IN ('class', 'league')),
  scope_id TEXT NOT NULL,
  method TEXT NOT NULL,
  source_version INTEGER NOT NULL,
  scored_at TEXT NOT NULL,
  player_count INTEGER NOT NULL,
  PRIMARY KEY (scope, scope_id, method)
);

-- Score columns are untyped on purpose: values round-trip exactly as the
-- scorer produced them (an int stays an int), so exports match byte for byte.
CREATE TABLE run_results (
  scope TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  method TEXT NOT NULL,
  player_id TEXT NOT NULL,
  model_rank INTEGER NOT NULL,
  name TEXT,
  position TEXT,
  age,
  player_type TEXT NOT NULL,
  model_score,
  raw_overall_score,
  position_player_score,
  batting_score,
  fielding_score,
  running_score,
  best_position TEXT,
  pitcher_score,
  starter_score,
  reliever_score,
  in_game_overall,
  in_game_potential,
  demand TEXT,
  breakdown TEXT NOT NULL,
  PRIMARY KEY (scope, scope_id, method, player_id),
  FOREIGN KEY (scope, scope_id, method)
    REFERENCES model_runs (scope, scope_id, method) ON DELETE CASCADE
);

CREATE INDEX run_results_order ON run_results (scope, scope_id, method, model_rank);
"""

# Trade lists and their entries list in insertion (rowid) order; an upsert or a
# rename updates in place, so it keeps its spot. The name / position / org on an
# entry are captured when the player is added, so the entry still renders once
# the player has left the league's snapshot.
_SCHEMA_V2 = """
CREATE TABLE trade_lists (
  league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at TEXT,
  PRIMARY KEY (league_id, id)
);

CREATE TABLE trade_list_entries (
  league_id TEXT NOT NULL,
  list_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  priority TEXT,
  note TEXT NOT NULL DEFAULT '',
  added_at TEXT,
  name TEXT NOT NULL DEFAULT '',
  position TEXT NOT NULL DEFAULT '',
  org TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (league_id, list_id, player_id),
  FOREIGN KEY (league_id, list_id)
    REFERENCES trade_lists (league_id, id) ON DELETE CASCADE
);
"""


def _run_script(conn, script):
    # Not `executescript`: it COMMITs any open transaction first, which would
    # break the all-or-nothing migration.
    for statement in script.split(";\n"):
        if statement.strip():
            conn.execute(statement)


def _migration_1(conn):
    _run_script(conn, _SCHEMA_V1)
    import db_import

    db_import.import_legacy_files(_path_of(conn).parent)


def _migration_2(conn):
    _run_script(conn, _SCHEMA_V2)
    import db_import

    db_import.import_trade_lists(_path_of(conn).parent)


# index i holds the step that takes the schema from version i to i + 1
_MIGRATIONS = [_migration_1, _migration_2]

_conns: "dict[tuple, sqlite3.Connection]" = {}
_conns_lock = threading.Lock()
_migrate_lock = threading.RLock()
_tx_depth: "dict[int, int]" = {}


def db_path() -> Path:
    from context import default_base_dir  # context imports this module

    return default_base_dir() / DB_FILENAME


def _path_of(conn) -> Path:
    return Path(conn.execute("PRAGMA database_list").fetchone()[2])


def connect() -> sqlite3.Connection:
    """This thread's connection to the current $DATA_DIR database, opened (and
    migrated) on first use."""
    path = str(db_path())
    key = (threading.get_ident(), path)
    conn = _conns.get(key)
    if conn is not None:
        return conn
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit, with explicit BEGIN in `transaction()`.
    # check_same_thread=False only so `close_all` can close it from elsewhere;
    # each connection is still used by the one thread that opened it.
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    # Registered before migrating so the importer can use the normal module
    # helpers: their `connect()` / `transaction()` join this migration.
    with _conns_lock:
        _conns[key] = conn
    try:
        _migrate(conn)
    except BaseException:
        with _conns_lock:
            _conns.pop(key, None)
        conn.close()
        raise
    return conn


def _migrate(conn) -> None:
    with _migrate_lock:
        if conn.execute("PRAGMA user_version").fetchone()[0] >= len(_MIGRATIONS):
            return
        conn.execute("BEGIN IMMEDIATE")
        _tx_depth[id(conn)] = 1
        try:
            # re-read under the write lock: another process may have migrated
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for step in range(version, len(_MIGRATIONS)):
                _MIGRATIONS[step](conn)
                conn.execute(f"PRAGMA user_version = {step + 1}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            _tx_depth.pop(id(conn), None)


@contextmanager
def transaction():
    """A write transaction on this thread's connection. Nested uses join the
    outermost one, so helpers can wrap their own writes and still compose."""
    conn = connect()
    depth = _tx_depth.get(id(conn), 0)
    if depth:
        _tx_depth[id(conn)] = depth + 1
        try:
            yield conn
        finally:
            _tx_depth[id(conn)] = depth
        return
    conn.execute("BEGIN IMMEDIATE")
    _tx_depth[id(conn)] = 1
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        _tx_depth.pop(id(conn), None)


def query(sql, params=()) -> list:
    return connect().execute(sql, params).fetchall()


def query_one(sql, params=()):
    return connect().execute(sql, params).fetchone()


def execute(sql, params=()):
    """A single write statement in its own transaction."""
    with transaction() as conn:
        return conn.execute(sql, params)


def close_all() -> None:
    """Close every open connection (tests, between data directories)."""
    with _conns_lock:
        conns = list(_conns.values())
        _conns.clear()
    for conn in conns:
        try:
            conn.close()
        except sqlite3.Error:
            pass
