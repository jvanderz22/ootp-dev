"""Leagues - the `leagues` table.

A *league* is a StatsPlus association: it owns the league's StatsPlus home URL,
(optionally) a default `lid`, and its own StatsPlus auth cookie (`sessionid` /
`csrftoken`). Every draft class is assigned to at most one league
(`draft_classes.league_id`). "Refresh drafted" for a class hits its league's URL
with that league's cookie.

The cookie values are secret: they live on the (private) data volume and are
never returned to clients - the API exposes only `has_sessionid` /
`has_csrftoken` (see `public_league`). Installs that predate the database had
their leagues in leagues.json / web_config.json; `db_import` folds those in.
"""
import json
import re

import db
from statsplus_api import normalize_league_url
from web.settings import clean_cookie_value

_FIELDS = (
    "id", "name", "league_url", "default_lid", "sessionid", "csrftoken",
    "game_league_ids",
)
_COOKIE_KEYS = ("sessionid", "csrftoken")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "league"


def _unique_id(base: str, taken) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base}-{i}" in taken:
        i += 1
    return f"{base}-{i}"


def _normalize_url(value):
    if value is None:
        return None
    value = value.strip()
    return normalize_league_url(value) if value else ""


def _clean_league_ids(value) -> list:
    """The OOTP in-game league ids that make up a league, as a sorted list of
    unique positive ints. Tolerant of a list, a comma/space string, or None
    (-> `[]`). An empty list means "no scoping" - every org in the snapshot."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[,\s]+", value.strip())
    out = set()
    for item in value or []:
        n = None
        try:
            n = int(str(item).strip())
        except (TypeError, ValueError):
            n = None
        if n:
            out.add(abs(n))
    return sorted(out)


def _clean(league: dict) -> dict:
    """Storage projection - keeps the secret cookie values. Never hand this
    straight to a client; use `public_league`."""
    return {
        "id": league.get("id"),
        "name": league.get("name") or league.get("id") or "",
        "league_url": league.get("league_url") or "",
        "default_lid": league.get("default_lid") or None,
        "sessionid": league.get("sessionid") or "",
        "csrftoken": league.get("csrftoken") or "",
        "game_league_ids": _clean_league_ids(league.get("game_league_ids")),
    }


def public_league(league: dict) -> dict:
    """Client-safe projection: the cookie values are replaced with the booleans
    `has_sessionid` / `has_csrftoken`."""
    return {
        "id": league.get("id"),
        "name": league.get("name") or league.get("id") or "",
        "league_url": league.get("league_url") or "",
        "default_lid": league.get("default_lid") or None,
        "has_sessionid": bool(league.get("sessionid")),
        "has_csrftoken": bool(league.get("csrftoken")),
        "game_league_ids": _clean_league_ids(league.get("game_league_ids")),
    }


# --------------------------------------------------------------------- storage
def _from_row(row) -> dict:
    league = dict(row)
    league["game_league_ids"] = json.loads(league.get("game_league_ids") or "[]")
    return _clean(league)


def _save(league: dict) -> None:
    """Insert or replace one league (stored in its `_clean` projection)."""
    league = _clean(league)
    values = [league[k] for k in _FIELDS]
    values[_FIELDS.index("game_league_ids")] = json.dumps(league["game_league_ids"])
    db.execute(
        f"INSERT INTO leagues ({', '.join(_FIELDS)}) VALUES ({', '.join('?' * len(_FIELDS))}) "
        "ON CONFLICT(id) DO UPDATE SET "
        + ", ".join(f"{k} = excluded.{k}" for k in _FIELDS if k != "id"),
        values,
    )


def load_leagues() -> list:
    # rowid order = creation order, which is what the old leagues.json list kept
    return [_from_row(r) for r in db.query("SELECT * FROM leagues ORDER BY rowid")]


def get_league(league_id: str):
    if not league_id:
        return None
    row = db.query_one("SELECT * FROM leagues WHERE id = ?", (league_id,))
    return _from_row(row) if row else None


# -------------------------------------------------------------- class <-> league
def explicit_class_league_id(name: str):
    row = db.query_one("SELECT league_id FROM draft_classes WHERE name = ?", (name,))
    return (row["league_id"] if row else None) or None


def league_for_class(name: str):
    """The league a class belongs to: its explicit `league_id`, or - when the
    class has none - the sole league if exactly one is configured."""
    explicit = explicit_class_league_id(name)
    if explicit:
        return get_league(explicit)
    leagues = load_leagues()
    return leagues[0] if len(leagues) == 1 else None


def class_names_for_league(league_id: str) -> list:
    """Classes *explicitly* pinned to `league_id`. The single-league fallback in
    `league_for_class` is deliberately not applied here: an unpinned class counts
    as unmapped for listing / assignment purposes (see the Settings page)."""
    rows = db.query(
        "SELECT name FROM draft_classes WHERE league_id = ? ORDER BY name", (league_id,)
    )
    return [r["name"] for r in rows]


def _set_league_id(conn, names, league_id) -> None:
    conn.executemany(
        "UPDATE draft_classes SET league_id = ?, revision = revision + 1 WHERE name = ?",
        [(league_id, n) for n in names],
    )


def set_class_league(name: str, league_id):
    if league_id and get_league(league_id) is None:
        raise ValueError(f"Unknown league {league_id!r}.")
    with db.transaction() as conn:
        _set_league_id(conn, [name], league_id or None)


def assign_classes(league_id: str, class_names) -> None:
    """Make `class_names` (and only those) explicitly belong to `league_id`,
    clearing the `league_id` of any class previously pinned to it."""
    if class_names is None:
        return
    wanted = set(class_names)
    with db.transaction() as conn:
        dropped = [n for n in class_names_for_league(league_id) if n not in wanted]
        _set_league_id(conn, dropped, None)
        _set_league_id(conn, sorted(wanted), league_id)


# --------------------------------------------------------------------- mutations
def create_league(
    name: str,
    league_url=None,
    default_lid=None,
    class_names=None,
    sessionid=None,
    csrftoken=None,
    game_league_ids=None,
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("League name is required.")
    leagues = load_leagues()
    league = _clean(
        {
            "id": _unique_id(_slugify(name), {x["id"] for x in leagues}),
            "name": name,
            "league_url": _normalize_url(league_url) or "",
            "default_lid": default_lid or None,
            "sessionid": clean_cookie_value(sessionid or "", "sessionid"),
            "csrftoken": clean_cookie_value(csrftoken or "", "csrftoken"),
            "game_league_ids": _clean_league_ids(game_league_ids),
        }
    )
    with db.transaction():
        _save(league)
        assign_classes(league["id"], class_names)
    return league


def update_league(
    league_id: str,
    name=None,
    league_url=None,
    default_lid=None,
    class_names=None,
    sessionid=None,
    csrftoken=None,
    game_league_ids=None,
) -> dict:
    target = get_league(league_id)
    if target is None:
        raise ValueError(f"Unknown league {league_id!r}.")
    if name is not None and name.strip():
        target["name"] = name.strip()
    if league_url is not None:
        target["league_url"] = _normalize_url(league_url) or ""
    if default_lid is not None:
        target["default_lid"] = default_lid or None
    # an explicit list (empty included) replaces; None means "leave as stored"
    if game_league_ids is not None:
        target["game_league_ids"] = _clean_league_ids(game_league_ids)
    # cookie fields follow the settings-page convention: a blank value means
    # "keep what's stored", a non-blank one replaces it.
    if sessionid is not None and sessionid.strip():
        target["sessionid"] = clean_cookie_value(sessionid, "sessionid")
    if csrftoken is not None and csrftoken.strip():
        target["csrftoken"] = clean_cookie_value(csrftoken, "csrftoken")
    with db.transaction():
        _save(target)
        assign_classes(league_id, class_names)
    return _clean(target)


def delete_league(league_id: str) -> str:
    """Delete the league. Its classes become unassigned and its snapshot / refresh
    rows go with it (foreign keys)."""
    with db.transaction() as conn:
        if conn.execute("DELETE FROM leagues WHERE id = ?", (league_id,)).rowcount == 0:
            raise ValueError(f"Unknown league {league_id!r}.")
    return league_id
