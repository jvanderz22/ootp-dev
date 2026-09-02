"""StatsPlus HTTP API client - replaces the Selenium draft-board scrape.

`GET <league-url>/api/draftv2/?lid=<optional>` returns a CSV of every pick so far,
including the OOTP player `ID`, which lets us match drafted players exactly
instead of parsing "POS Firstname Lastname" strings.

`<league-url>` is the league's StatsPlus home, e.g. `https://statsplus.net/yfmlb/`
or `https://atl-01.statsplus.net/wbf/`.

Auth is a browser session cookie (there is no API-key scheme): copy `sessionid`
and `csrftoken` from a logged-in StatsPlus tab (DevTools -> Application ->
Cookies) into the app settings as `sessionid=<v>; csrftoken=<v>`.
"""
import csv
import io
from dataclasses import asdict, dataclass
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


def _draft_url(league_url: str) -> str:
    return normalize_league_url(league_url).rstrip("/") + "/api/draftv2/"


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

    return _parse_draft_csv(body)


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
