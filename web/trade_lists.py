"""Custom trade-target lists - the `trade_lists` / `trade_list_entries` tables.

A *trade list* is a named, per-league collection of players a GM is chasing in
trade. Each entry carries a priority tier (`HIGH` / `MEDIUM` / `LOW`) and a
free-text note. Lists hang off the league row, not its snapshot, so refreshing a
snapshot never touches them; deleting the league deletes them (FK cascade).

This module is pure CRUD: it knows nothing about snapshots, scoring, or GraphQL.
Every function returns a list as `{"id", "name", "createdAt", "entries": [...]}`
with entries in add order. An entry keeps a denormalized `name` / `position` /
`org` captured at add-time so a list still renders sensibly when a player has
since left the league's snapshot. Callers surface `ValueError` as an
`InvalidInput` GraphQL error, matching `web/leagues.py`. Installs that predate
the database kept these in trade_lists.json; `db_import` folds that in.
"""
import re
from datetime import datetime, timezone

import db

PRIORITIES = ("HIGH", "MEDIUM", "LOW")
_PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}
_DENORM = ("name", "position", "org")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "list"


def _unique_id(base: str, taken) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base}-{i}" in taken:
        i += 1
    return f"{base}-{i}"


def priority_rank(priority) -> int:
    """Numeric backing for sorting; unknown / missing sorts last."""
    return _PRIORITY_RANK.get(priority, len(PRIORITIES))


def _clean_priority(value, *, default="MEDIUM"):
    if value is None:
        return default
    value = str(value).strip().upper()
    if value not in _PRIORITY_RANK:
        raise ValueError(
            f"Unknown priority {value!r}; expected one of {', '.join(PRIORITIES)}."
        )
    return value


# ----------------------------------------------------------------------- reads
def _entry(row) -> dict:
    return {
        "playerId": row["player_id"],
        "priority": row["priority"],
        "note": row["note"],
        "addedAt": row["added_at"],
        "name": row["name"],
        "position": row["position"],
        "org": row["org"],
    }


def lists_for_league(league_id: str) -> list:
    lists = {
        r["id"]: {"id": r["id"], "name": r["name"], "createdAt": r["created_at"], "entries": []}
        for r in db.query(
            "SELECT id, name, created_at FROM trade_lists WHERE league_id = ? ORDER BY rowid",
            (league_id,),
        )
    }
    for r in db.query(
        "SELECT * FROM trade_list_entries WHERE league_id = ? ORDER BY rowid", (league_id,)
    ):
        lists[r["list_id"]]["entries"].append(_entry(r))
    return list(lists.values())


def get_list(league_id: str, list_id: str):
    row = db.query_one(
        "SELECT id, name, created_at FROM trade_lists WHERE league_id = ? AND id = ?",
        (league_id, list_id),
    )
    if row is None:
        return None
    entries = db.query(
        "SELECT * FROM trade_list_entries WHERE league_id = ? AND list_id = ? ORDER BY rowid",
        (league_id, list_id),
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "createdAt": row["created_at"],
        "entries": [_entry(r) for r in entries],
    }


def _require_list(league_id: str, list_id: str) -> dict:
    lst = get_list(league_id, list_id)
    if lst is None:
        raise ValueError(f"Trade list {list_id!r} not found.")
    return lst


def _require_entry(league_id: str, list_id: str, player_id: str) -> None:
    if db.query_one(
        "SELECT 1 FROM trade_list_entries WHERE league_id = ? AND list_id = ? AND player_id = ?",
        (league_id, list_id, player_id),
    ) is None:
        raise ValueError(f"Player {player_id!r} is not on list {list_id!r}.")


# ------------------------------------------------------------------- list CRUD
def create_list(league_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("List name is required.")
    with db.transaction() as conn:
        taken = {
            r["id"]
            for r in conn.execute("SELECT id FROM trade_lists WHERE league_id = ?", (league_id,))
        }
        list_id = _unique_id(_slugify(name), taken)
        conn.execute(
            "INSERT INTO trade_lists (league_id, id, name, created_at) VALUES (?, ?, ?, ?)",
            (league_id, list_id, name, _now()),
        )
        return get_list(league_id, list_id)


def rename_list(league_id: str, list_id: str, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("List name is required.")
    with db.transaction() as conn:
        _require_list(league_id, list_id)
        conn.execute(
            "UPDATE trade_lists SET name = ? WHERE league_id = ? AND id = ?",
            (name, league_id, list_id),
        )
        return get_list(league_id, list_id)


def delete_list(league_id: str, list_id: str) -> str:
    cur = db.execute(
        "DELETE FROM trade_lists WHERE league_id = ? AND id = ?", (league_id, list_id)
    )
    if not cur.rowcount:
        raise ValueError(f"Trade list {list_id!r} not found.")
    return list_id


# ------------------------------------------------------------------ entry CRUD
def add_entry(
    league_id: str,
    list_id: str,
    player_id: str,
    priority=None,
    note=None,
    denorm=None,
) -> dict:
    """Upsert by `playerId`: re-adding a player patches the existing entry rather
    than duplicating it. `denorm` carries the add-time `name` / `position` /
    `org` snapshot used to render stale entries."""
    player_id = str(player_id).strip()
    if not player_id:
        raise ValueError("Player id is required.")
    priority = _clean_priority(priority)
    denorm = denorm or {}
    with db.transaction() as conn:
        _require_list(league_id, list_id)
        # On a re-add only the values given replace the stored ones; a missing
        # note / denorm field keeps what is there.
        conn.execute(
            """
            INSERT INTO trade_list_entries
              (league_id, list_id, player_id, priority, note, added_at, name, position, org)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (league_id, list_id, player_id) DO UPDATE SET
              priority = excluded.priority,
              note = CASE WHEN ? THEN excluded.note ELSE note END,
              name = CASE WHEN ? THEN excluded.name ELSE name END,
              position = CASE WHEN ? THEN excluded.position ELSE position END,
              org = CASE WHEN ? THEN excluded.org ELSE org END
            """,
            (
                league_id, list_id, player_id, priority, note or "", _now(),
                *(denorm.get(k) or "" for k in _DENORM),
                note is not None,
                *(denorm.get(k) is not None for k in _DENORM),
            ),
        )
        return get_list(league_id, list_id)


def remove_entry(league_id: str, list_id: str, player_id: str) -> dict:
    player_id = str(player_id).strip()
    with db.transaction() as conn:
        _require_list(league_id, list_id)
        _require_entry(league_id, list_id, player_id)
        conn.execute(
            "DELETE FROM trade_list_entries WHERE league_id = ? AND list_id = ? AND player_id = ?",
            (league_id, list_id, player_id),
        )
        return get_list(league_id, list_id)


def set_entry(
    league_id: str,
    list_id: str,
    player_id: str,
    priority=None,
    note=None,
) -> dict:
    """Patch `priority` and/or `note` on an existing entry. `None` leaves a field
    as stored; pass an empty string to clear a note."""
    player_id = str(player_id).strip()
    with db.transaction() as conn:
        _require_list(league_id, list_id)
        _require_entry(league_id, list_id, player_id)
        if priority is not None:
            priority = _clean_priority(priority)
        conn.execute(
            """
            UPDATE trade_list_entries
               SET priority = COALESCE(?, priority), note = COALESCE(?, note)
             WHERE league_id = ? AND list_id = ? AND player_id = ?
            """,
            (priority, note, league_id, list_id, player_id),
        )
        return get_list(league_id, list_id)
