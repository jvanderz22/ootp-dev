"""Leagues stored as leagues.json under DATA_DIR.

A *league* is a StatsPlus association: it owns the league's StatsPlus home URL
and (optionally) a default `lid`. Every draft class is assigned to at most one
league; that assignment is persisted as `league_id` inside the class's own
`processed_classes/<name>/config.json`. "Refresh drafted" for a class hits its
league's URL. The session cookies stay app-wide (see web/settings.py).
"""
import json
import re

from context import DraftClassContext, default_base_dir
from io_utils import atomic_write_json
from statsplus_api import normalize_league_url

_FILENAME = "leagues.json"
_FIELDS = ("id", "name", "league_url", "default_lid")


def _path():
    return default_base_dir() / _FILENAME


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


def _clean(league: dict) -> dict:
    return {
        "id": league.get("id"),
        "name": league.get("name") or league.get("id") or "",
        "league_url": league.get("league_url") or "",
        "default_lid": league.get("default_lid") or None,
    }


# --------------------------------------------------------------------- storage
def _write(leagues) -> None:
    atomic_write_json(_path(), {"leagues": [_clean(x) for x in leagues]})


def load_leagues() -> list:
    try:
        with open(_path()) as f:
            data = json.load(f)
        leagues = [_clean(x) for x in data.get("leagues", []) if x.get("id")]
        return leagues
    except (FileNotFoundError, json.JSONDecodeError):
        return _migrate_from_legacy()


def _migrate_from_legacy() -> list:
    """First run after the leagues upgrade: fold the old single app-wide
    `league_url` / `default_lid` (web_config.json) into one 'Default' league."""
    from web.settings import legacy_league_config

    legacy = legacy_league_config()
    url = legacy.get("league_url") or ""
    if not url:
        _write([])
        return []
    name = ""
    m = re.search(r"/([^/]+)/?$", url.rstrip("/"))
    if m:
        name = m.group(1)
    league = _clean(
        {
            "id": _slugify(name) if name else "default",
            "name": name or "Default",
            "league_url": url,
            "default_lid": legacy.get("default_lid"),
        }
    )
    _write([league])
    return [league]


def get_league(league_id: str):
    if not league_id:
        return None
    for league in load_leagues():
        if league["id"] == league_id:
            return league
    return None


# -------------------------------------------------------------- class <-> league
def _load_class_config(name: str) -> dict:
    ctx = DraftClassContext(name)
    try:
        return ctx.load_config()
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_class_league_id(name: str, league_id) -> None:
    ctx = DraftClassContext(name)
    config = _load_class_config(name)
    if league_id:
        config["league_id"] = league_id
    else:
        config.pop("league_id", None)
    ctx.processed_dir.mkdir(parents=True, exist_ok=True)
    ctx.save_config(config)


def explicit_class_league_id(name: str):
    return _load_class_config(name).get("league_id") or None


def league_for_class(name: str):
    """The league a class belongs to: its explicit `league_id`, or - when the
    class has none - the sole league if exactly one is configured."""
    leagues = load_leagues()
    explicit = explicit_class_league_id(name)
    if explicit:
        for league in leagues:
            if league["id"] == explicit:
                return league
        return None
    return leagues[0] if len(leagues) == 1 else None


def class_names_for_league(league_id: str) -> list:
    out = []
    for name in DraftClassContext.list_classes():
        league = league_for_class(name)
        if league and league["id"] == league_id:
            out.append(name)
    return sorted(out)


def set_class_league(name: str, league_id):
    if league_id and get_league(league_id) is None:
        raise ValueError(f"Unknown league {league_id!r}.")
    _save_class_league_id(name, league_id)


def assign_classes(league_id: str, class_names) -> None:
    """Make `class_names` (and only those) explicitly belong to `league_id`,
    clearing the `league_id` of any class previously pinned to it."""
    if class_names is None:
        return
    wanted = set(class_names)
    for name in DraftClassContext.list_classes():
        if name in wanted:
            _save_class_league_id(name, league_id)
        elif explicit_class_league_id(name) == league_id:
            _save_class_league_id(name, None)


# --------------------------------------------------------------------- mutations
def create_league(name: str, league_url=None, default_lid=None, class_names=None) -> dict:
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
        }
    )
    leagues.append(league)
    _write(leagues)
    assign_classes(league["id"], class_names)
    return league


def update_league(
    league_id: str, name=None, league_url=None, default_lid=None, class_names=None
) -> dict:
    leagues = load_leagues()
    target = next((x for x in leagues if x["id"] == league_id), None)
    if target is None:
        raise ValueError(f"Unknown league {league_id!r}.")
    if name is not None and name.strip():
        target["name"] = name.strip()
    if league_url is not None:
        target["league_url"] = _normalize_url(league_url) or ""
    if default_lid is not None:
        target["default_lid"] = default_lid or None
    _write(leagues)
    assign_classes(league_id, class_names)
    return _clean(target)


def delete_league(league_id: str) -> str:
    leagues = load_leagues()
    if not any(x["id"] == league_id for x in leagues):
        raise ValueError(f"Unknown league {league_id!r}.")
    _write([x for x in leagues if x["id"] != league_id])
    for name in DraftClassContext.list_classes():
        if explicit_class_league_id(name) == league_id:
            _save_class_league_id(name, None)
    return league_id
