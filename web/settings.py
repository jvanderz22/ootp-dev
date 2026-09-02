"""App settings stored as web_config.json under DATA_DIR.

Holds the StatsPlus league URL + the two auth cookie values (`sessionid`,
`csrftoken`) used by the drafted-players refresh. Those values are secret: they
are written to the (private) data volume and never returned to clients - the API
exposes only `has_sessionid` / `has_csrftoken`.
"""
import json
import os
import re

from context import default_base_dir
from io_utils import atomic_write_json
from statsplus_api import StatsPlusError, normalize_league_url

_FILENAME = "web_config.json"
_DEFAULTS = {"league_url": "", "sessionid": "", "csrftoken": "", "default_lid": None}
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


def load_settings() -> dict:
    data = dict(_DEFAULTS)
    try:
        with open(_path()) as f:
            stored = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stored = {}
    if isinstance(stored, dict):
        data.update({k: stored.get(k, v) for k, v in _DEFAULTS.items()})
        if not data["league_url"] and stored.get("league_slug"):  # migrate old key
            data["league_url"] = _safe_normalize(stored["league_slug"])
        if not (data["sessionid"] or data["csrftoken"]) and stored.get("cookie"):
            data.update(_split_cookie_header(stored["cookie"]))

    # env fallbacks (useful for a first deploy before the settings page is used)
    if not data["league_url"]:
        data["league_url"] = _safe_normalize(
            os.environ.get("STATSPLUS_LEAGUE_URL")
            or os.environ.get("STATSPLUS_LEAGUE_SLUG", "")
        )
    if not (data["sessionid"] or data["csrftoken"]):
        env_sid = os.environ.get("STATSPLUS_SESSIONID", "")
        env_csrf = os.environ.get("STATSPLUS_CSRFTOKEN", "")
        if env_sid or env_csrf:
            data["sessionid"] = clean_cookie_value(env_sid, "sessionid")
            data["csrftoken"] = clean_cookie_value(env_csrf, "csrftoken")
        elif os.environ.get("STATSPLUS_COOKIE"):
            data.update(_split_cookie_header(os.environ["STATSPLUS_COOKIE"]))
    return data


def _safe_normalize(value) -> str:
    try:
        return normalize_league_url(value or "")
    except StatsPlusError:
        return (value or "").strip()


def update_settings(
    league_url=None, sessionid=None, csrftoken=None, default_lid=None
) -> dict:
    current = load_settings()
    if league_url is not None:
        current["league_url"] = normalize_league_url(league_url)
    if sessionid is not None and sessionid.strip():
        current["sessionid"] = clean_cookie_value(sessionid, "sessionid")
    if csrftoken is not None and csrftoken.strip():
        current["csrftoken"] = clean_cookie_value(csrftoken, "csrftoken")
    if default_lid is not None:
        current["default_lid"] = default_lid or None
    atomic_write_json(_path(), current)
    return current


def cookie_header(settings=None) -> str:
    s = settings or load_settings()
    parts = [f"{k}={s[k]}" for k in _COOKIE_KEYS if s.get(k)]
    return "; ".join(parts)


def public_settings(settings=None) -> dict:
    s = settings or load_settings()
    return {
        "league_url": s.get("league_url") or None,
        "default_lid": s.get("default_lid"),
        "has_sessionid": bool(s.get("sessionid")),
        "has_csrftoken": bool(s.get("csrftoken")),
    }
