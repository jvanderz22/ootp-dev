"""Legacy StatsPlus config reader - kept only to seed leagues on upgrade.

The StatsPlus auth cookie (`sessionid`, `csrftoken`) is now **per league** and
lives in leagues.json (see web/leagues.py). This module survives only to fold
the old app-wide values - `web_config.json` or the `STATSPLUS_*` env vars - into
the leagues store the first time it is read. Nothing here is part of the live
settings surface any more.
"""
import json
import os
import re

from context import default_base_dir
from statsplus_api import StatsPlusError, normalize_league_url

_FILENAME = "web_config.json"
_COOKIE_KEYS = ("sessionid", "csrftoken")


def _path():
    return default_base_dir() / _FILENAME


def clean_cookie_value(value: str, name: str) -> str:
    """Be forgiving about what gets pasted: accept the bare value, `name=value`,
    or even a full `sessionid=…; csrftoken=…` blob pasted into one field."""
    value = (value or "").strip().strip(";").strip()
    if not value:
        return ""
    m = re.search(rf"{name}\s*=\s*([^;\s]+)", value)
    if m:
        return m.group(1)
    if "=" in value:  # pasted `othername=value` - take the value part
        return value.split("=", 1)[1].strip().strip(";").strip()
    return value


def _split_cookie_header(header: str) -> dict:
    out = {}
    for key in _COOKIE_KEYS:
        out[key] = clean_cookie_value(header, key)
    return out


def _read_raw() -> dict:
    try:
        with open(_path()) as f:
            stored = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return stored if isinstance(stored, dict) else {}


def legacy_cookie() -> dict:
    """The old app-wide `sessionid` / `csrftoken` (from `web_config.json` or the
    `STATSPLUS_*` env vars), read once by web/leagues.py to seed leagues on
    upgrade. Returns only the keys that are actually set - `{}` if none are."""
    stored = _read_raw()
    data = {k: stored.get(k, "") or "" for k in _COOKIE_KEYS}
    if not (data["sessionid"] or data["csrftoken"]) and stored.get("cookie"):
        data.update(_split_cookie_header(stored["cookie"]))

    if not (data["sessionid"] or data["csrftoken"]):
        env_sid = os.environ.get("STATSPLUS_SESSIONID", "")
        env_csrf = os.environ.get("STATSPLUS_CSRFTOKEN", "")
        if env_sid or env_csrf:
            data["sessionid"] = clean_cookie_value(env_sid, "sessionid")
            data["csrftoken"] = clean_cookie_value(env_csrf, "csrftoken")
        elif os.environ.get("STATSPLUS_COOKIE"):
            data.update(_split_cookie_header(os.environ["STATSPLUS_COOKIE"]))
    return {k: v for k, v in data.items() if v}


def _safe_normalize(value) -> str:
    try:
        return normalize_league_url(value or "")
    except StatsPlusError:
        return (value or "").strip()


def legacy_league_config() -> dict:
    """The old app-wide league URL / lid, read from web_config.json (or the
    STATSPLUS_LEAGUE_* env vars). Consumed once by web/leagues.py to seed the
    first League on upgrade; not part of the live settings surface any more."""
    stored = _read_raw()
    league_url = _safe_normalize(
        stored.get("league_url")
        or stored.get("league_slug")
        or os.environ.get("STATSPLUS_LEAGUE_URL")
        or os.environ.get("STATSPLUS_LEAGUE_SLUG", "")
    )
    return {"league_url": league_url, "default_lid": stored.get("default_lid")}


def cookie_header(source=None) -> str:
    """`sessionid=…; csrftoken=…` built from a mapping - a `web/leagues.py`
    league dict, or any dict carrying those keys. Empty string if neither is set."""
    s = source or {}
    parts = [f"{k}={s[k]}" for k in _COOKIE_KEYS if s.get(k)]
    return "; ".join(parts)
