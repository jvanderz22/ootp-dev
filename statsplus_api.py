"""StatsPlus HTTP API client - replaces the Selenium draft-board scrape.

`GET <league-url>/api/draftv2/?lid=<optional>` returns a CSV of every pick so far,
including the OOTP player `ID`, which lets us match drafted players exactly
instead of parsing "POS Firstname Lastname" strings.

`<league-url>` is the league's StatsPlus home, e.g. `https://statsplus.net/yfmlb/`
or `https://atl-01.statsplus.net/wbf/`. Either form is accepted, but every
`/api/` request is sent to the canonical apex host `statsplus.net/<slug>/`: the
per-node subdomains (`atl-01.statsplus.net`, ...) are OOTP game-server hosts and
do not carry the StatsPlus web session, so the API answers there with
"This API requires user to be logged in, visit https://statsplus.net/<slug>/ ...".

Auth is a browser session cookie (there is no API-key scheme): copy `sessionid`
and `csrftoken` from a logged-in StatsPlus tab (DevTools -> Application ->
Cookies) into the app settings as `sessionid=<v>; csrftoken=<v>`.
"""
import csv
import io
import re
import time
from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

DRAFTED_FIELDNAMES = ["id", "name", "position", "round", "pick", "overall", "team"]

_STATSPLUS_DOMAIN = "statsplus.net"


class StatsPlusAuthError(RuntimeError):
    """Raised when StatsPlus rejects the session cookie (expired / missing)."""


class StatsPlusError(RuntimeError):
    pass


@dataclass
class DraftPick:
    id: str
    name: str
    position: str
    round: str
    pick: str
    overall: str
    team: str


def normalize_league_url(value: str) -> str:
    """Accept a full URL (`https://statsplus.net/yfmlb/`, `atl-01.statsplus.net/wbf`)
    or a bare slug (`yfmlb`) and return a normalised `scheme://host/path/` string.
    Returns "" for empty input; raises StatsPlusError for a non-StatsPlus host."""
    value = (value or "").strip()
    if not value:
        return ""

    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)

    host = parsed.netloc.lower()
    path = parsed.path
    if "." not in host:
        # bare slug like "yfmlb" -> parsed as host; treat as statsplus.net/<slug>
        host, path = _STATSPLUS_DOMAIN, f"/{value.strip('/')}"

    if not (host == _STATSPLUS_DOMAIN or host.endswith("." + _STATSPLUS_DOMAIN)):
        raise StatsPlusError(f"{host!r} is not a statsplus.net host.")

    path = "/" + path.strip("/")
    if not path.rstrip("/"):
        raise StatsPlusError("Missing the league slug in the StatsPlus URL.")
    return urlunparse(("https", host, path + "/", "", "", ""))


def statsplus_player_url(league_url: str, player_id) -> Optional[str]:
    """Public link to a player's page on the StatsPlus web app,
    ``https://statsplus.net/<slug>/player/<id>``. Uses the apex host (the web
    app is served there, like the API); returns ``None`` when the league has no
    usable StatsPlus URL or the id is missing."""
    pid = str(player_id or "").strip()
    if not pid:
        return None
    try:
        base = _canonical_league_url(league_url)
    except StatsPlusError:
        return None
    if not base:
        return None
    return f"{base.rstrip('/')}/player/{pid}"


def _canonical_league_url(league_url: str) -> str:
    """`normalize_league_url` but with the host forced to the apex
    `statsplus.net`. The API is only served there; a per-node subdomain
    (`atl-01.statsplus.net/wbf/`) reaches the OOTP game server, which has no
    StatsPlus session and rejects every `/api/` call with a "log in" notice.
    Only the league slug carries over."""
    normalized = normalize_league_url(league_url)
    if not normalized:
        return ""
    return urlunparse(
        ("https", _STATSPLUS_DOMAIN, urlparse(normalized).path, "", "", "")
    )


def _draft_url(league_url: str) -> str:
    return _canonical_league_url(league_url).rstrip("/") + "/api/draftv2/"


def fetch_draft_picks(league_url: str, cookie: str, lid=None, timeout: float = 30.0):
    if not (league_url or "").strip():
        raise StatsPlusError("StatsPlus league URL is not configured.")
    if not cookie:
        raise StatsPlusAuthError("StatsPlus session cookie is not configured.")

    import httpx

    params = {"lid": lid} if lid else {}
    headers = {"Cookie": cookie.strip(), "Accept": "text/csv, */*"}
    try:
        resp = httpx.get(
            _draft_url(league_url), params=params, headers=headers, timeout=timeout,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:  # noqa: F821 - httpx imported above
        raise StatsPlusError(f"Could not reach StatsPlus: {exc}") from exc

    if resp.status_code in (301, 302, 401, 403):
        raise StatsPlusAuthError(
            "StatsPlus rejected the session cookie - re-copy sessionid/csrftoken "
            "from a logged-in browser tab."
        )
    if resp.status_code >= 400:
        raise StatsPlusError(f"StatsPlus returned HTTP {resp.status_code}.")

    body = resp.text.strip()
    if not body:
        return []
    if body.lstrip().startswith("<"):  # got an HTML login page, not CSV
        raise StatsPlusAuthError("StatsPlus returned a login page instead of draft data.")
    if _looks_like_login_notice(body):
        raise StatsPlusAuthError(
            "StatsPlus rejected the session for this league (response: "
            f"{body[:160]!r}). Re-copy sessionid/csrftoken from a tab logged in "
            "at statsplus.net, and check the team link for this league."
        )

    return _parse_draft_csv(body)


# --------------------------------------------------------------------- league snapshot
#
# The draft-board scrape only ever needed `/api/draftv2/`. The live-league
# snapshot (see league_snapshot.py) pulls the whole player pool from three more
# endpoints, all under the same `<league-url>/api/` root and the same cookie:
#
#   GET /api/ratings/  -> fires an async CSV export, body carries a
#                         `.../api/mycsv/?request=<uuid>` poll URL (valid ~30 min)
#   GET <poll-url>     -> "...still in progress..." until ready, then the full CSV
#   GET /api/players/  -> biographical / roster / contract CSV (one row per player)
#   GET /api/teams/    -> id -> name CSV for the numeric team/org/league ids
#
# These return raw CSV text (unlike `fetch_draft_picks`, which returns parsed
# rows) so the join/rename logic downstream can be unit-tested against small
# fixture strings.

_MYCSV_URL_RE = re.compile(r"https?://[^\s\"'<>]+/api/mycsv/\?request=[0-9a-fA-F-]+")

# StatsPlus answers an unauthenticated `/api/` call with HTTP 200 and a short
# plain-text notice (not an HTML login page), so the `startswith("<")` check
# below misses it. Sniff the body for the notice and treat it as an auth error.
_LOGIN_NOTICE_MARKERS = (
    "requires user to be logged in",
    "log in to a linked team",
    "you must be logged in",
    "please log in",
    "not logged in",
)


def _looks_like_login_notice(body: str) -> bool:
    head = (body or "")[:500].lower()
    return any(marker in head for marker in _LOGIN_NOTICE_MARKERS)


def _api_url(league_url: str, endpoint: str) -> str:
    return _canonical_league_url(league_url).rstrip("/") + f"/api/{endpoint}/"


def _get_api_text(url: str, cookie: str, *, params=None, timeout: float = 60.0) -> str:
    """GET `url` with the StatsPlus session cookie and return the body text,
    applying the same auth / HTML-login detection as `fetch_draft_picks`."""
    if not (url or "").strip():
        raise StatsPlusError("StatsPlus league URL is not configured.")
    if not cookie:
        raise StatsPlusAuthError("StatsPlus session cookie is not configured.")

    import httpx

    headers = {"Cookie": cookie.strip(), "Accept": "text/csv, */*"}
    try:
        resp = httpx.get(
            url, params=params or None, headers=headers, timeout=timeout,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:  # noqa: F821 - httpx imported above
        raise StatsPlusError(f"Could not reach StatsPlus: {exc}") from exc

    if resp.status_code in (301, 302, 401, 403):
        raise StatsPlusAuthError(
            "StatsPlus rejected the session cookie - re-copy sessionid/csrftoken "
            "from a logged-in browser tab."
        )
    if resp.status_code >= 400:
        raise StatsPlusError(f"StatsPlus returned HTTP {resp.status_code}.")

    body = resp.text
    if body.lstrip().startswith("<"):  # got an HTML login page, not CSV
        raise StatsPlusAuthError("StatsPlus returned a login page instead of data.")
    if _looks_like_login_notice(body):
        raise StatsPlusAuthError(
            "StatsPlus rejected the session for this league (response: "
            f"{body.strip()[:160]!r}). Re-copy sessionid/csrftoken from a tab "
            "logged in at statsplus.net, and check the team link for this league."
        )
    return body


def start_ratings_job(league_url: str, cookie: str, timeout: float = 60.0) -> str:
    """Fire the async ratings export and return the poll URL parsed out of the
    `GET /api/ratings/` response body."""
    body = _get_api_text(_api_url(league_url, "ratings"), cookie, timeout=timeout)
    match = _MYCSV_URL_RE.search(body)
    if not match:
        raise StatsPlusError(
            "StatsPlus /api/ratings/ did not return an export URL "
            f"(response began {body[:200]!r})."
        )
    return match.group(0)


def poll_ratings_export(
    poll_url: str, cookie: str, timeout: float = 240.0, interval: float = 15.0,
    _sleep=time.sleep,
) -> str:
    """Poll `poll_url` until the export is ready and return the finished CSV text.
    Raises `StatsPlusError` if it is still in progress after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while True:
        body = _get_api_text(poll_url, cookie, timeout=60.0)
        if "in progress" not in body.lower():
            return body
        if time.monotonic() >= deadline:
            raise StatsPlusError(
                f"StatsPlus ratings export was still in progress after {timeout:.0f}s."
            )
        _sleep(interval)


def fetch_ratings(
    league_url: str, cookie: str, timeout: float = 240.0, interval: float = 15.0
) -> str:
    """Convenience: `start_ratings_job` + `poll_ratings_export` in one call."""
    poll_url = start_ratings_job(league_url, cookie)
    return poll_ratings_export(poll_url, cookie, timeout=timeout, interval=interval)


def fetch_players(league_url: str, cookie: str, timeout: float = 60.0) -> str:
    """Raw CSV text from `GET /api/players/` (one row per player)."""
    return _get_api_text(_api_url(league_url, "players"), cookie, timeout=timeout)


def fetch_league_date(league_url: str, cookie: str, timeout: float = 30.0) -> str:
    """The league's current in-game date (`GET /api/date/` -> e.g. `2042-05-19`).
    Cheap; used to decide whether a stored snapshot is out of date."""
    return _get_api_text(_api_url(league_url, "date"), cookie, timeout=timeout).strip()


def fetch_teams(league_url: str, cookie: str, timeout: float = 60.0) -> str:
    """Raw CSV text from `GET /api/teams/` (id -> name for teams/orgs/leagues)."""
    return _get_api_text(_api_url(league_url, "teams"), cookie, timeout=timeout)


def _parse_draft_csv(text: str):
    reader = csv.DictReader(io.StringIO(text))
    picks = []
    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        pick_id = norm.get("id", "")
        if not pick_id:
            continue
        picks.append(
            DraftPick(
                id=pick_id,
                name=norm.get("player name", ""),
                position=norm.get("position", ""),
                round=norm.get("round", ""),
                pick=norm.get("pick in round", ""),
                overall=norm.get("overall", ""),
                team=norm.get("team", ""),
            )
        )
    return picks


def write_drafted_players_file(ctx, picks) -> None:
    ctx.processed_dir.mkdir(parents=True, exist_ok=True)
    with open(ctx.drafted_players_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DRAFTED_FIELDNAMES)
        writer.writeheader()
        for pick in picks:
            writer.writerow(asdict(pick))
