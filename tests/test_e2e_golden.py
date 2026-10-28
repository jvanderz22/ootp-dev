"""End-to-end golden tests: drive the real app (GraphQL, the C+ CSV download and
the CLI scripts) over deterministic fixture data and compare every response to a
recorded golden file in `tests/golden/`.

They pin the app's observable output so a storage rewrite can prove it changed
nothing a user sees. Regenerate the goldens (only when an output change is
intended) with:

    UPDATE_GOLDEN=1 python3 -m pytest tests/test_e2e_golden.py

Floats compare with a small tolerance (XGBoost sums can differ in the last bits
between thread counts); timestamps are masked.

The `*_components.json` files are different: they hold every player's old flat
`components` dict, recorded from the pre-SQLite app (commit b6179fa), and are
never regenerated. `check_breakdowns` proves the typed `playerBreakdown` that
replaced it carries the same values for the side(s) the player is judged on.
"""
import json
import os
import re
import runpy
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from tests import e2e_fixtures

pytestmark = pytest.mark.slow

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"
TIMESTAMP_KEYS = {"fetchedAt", "lastProcessed", "startedAt", "finishedAt", "updatedAt"}

CLASS = "fx-draft"
LEAGUE_NAME = "Golden Fixture League"
LEAGUE_URL = "https://statsplus.net/goldenfx/"
LEAGUE_DATE = "2042-05-19"

PLAYER_FIELDS = """
  rank id name position bestPosition type age batHand throwHand org team level
  statsPlusUrl rule5Eligible modelScore inGameOverall inGamePotential demand
  drafted draftedTeam draftedPick draftedRound draftedRoundPick
  positionPlayerScore pitcherScore battingScoreComponent fieldingScoreComponent
  starterComponent relieverComponent runningScoreComponent rawOverallScore ratings
"""
CLASS_FIELDS = """
  name rankingMethod playerCount hasCustomOrder lastProcessed draftedCount
  leagueId leagueName
"""
LEAGUE_FIELDS = """
  id name leagueUrl defaultLid classNames updatedAt hasSessionid hasCsrftoken
  gameLeagueIds
"""
SNAPSHOT_FIELDS = "leagueId fetchedAt playerCount rankedMethods"
STATUS_FIELDS = f"leagueId state startedAt finishedAt error progress snapshot {{ {SNAPSHOT_FIELDS} }}"


# ---------------------------------------------------------------- golden I/O
def _normalize(value, key=None):
    if isinstance(value, dict):
        return {k: _normalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if key in TIMESTAMP_KEYS and value is not None:
        return "<timestamp>"
    return value


def _diff(expected, actual, path="$", out=None):
    out = [] if out is None else out
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            if k not in actual:
                out.append(f"{path}.{k}: missing (expected {expected[k]!r:.80})")
            elif k not in expected:
                out.append(f"{path}.{k}: unexpected {actual[k]!r:.80}")
            else:
                _diff(expected[k], actual[k], f"{path}.{k}", out)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path}: length {len(actual)} != expected {len(expected)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            _diff(e, a, f"{path}[{i}]", out)
    elif (
        isinstance(expected, (int, float)) and isinstance(actual, (int, float))
        and not isinstance(expected, bool) and not isinstance(actual, bool)
    ):
        if abs(expected - actual) > 1e-4 + 1e-6 * abs(expected):
            out.append(f"{path}: {actual!r} != expected {expected!r}")
    elif expected != actual:
        out.append(f"{path}: {actual!r:.120} != expected {expected!r:.120}")
    return out


def check_golden(name, data):
    path = GOLDEN_DIR / f"{name}.json"
    data = _normalize(json.loads(json.dumps(data)))
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"golden {path.name} missing - run with UPDATE_GOLDEN=1")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
        return
    diffs = _diff(json.loads(path.read_text()), data)
    assert not diffs, f"{len(diffs)} difference(s) vs {path.name}:\n" + "\n".join(diffs[:40])


# ------------------------------------------------------------------ helpers
@pytest.fixture
def client(data_dir, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    from starlette.testclient import TestClient

    from web.app import app

    return TestClient(app)


def gql(client, query, **variables):
    resp = client.post("/graphql", json={"query": query, "variables": variables})
    resp.raise_for_status()
    body = resp.json()
    assert "errors" not in body, body["errors"]
    return body["data"]


def upload_class(client, tmp_path, name=CLASS, method="draft_class", csv_text=None):
    src = tmp_path / f"{name}-upload.csv"
    src.write_text(csv_text or e2e_fixtures.make_draft_class_csv())
    q = (
        "mutation($file: Upload!, $name: String!, $method: String!) { "
        f"uploadDraftClass(name: $name, rankingMethod: $method, file: $file) {{ {CLASS_FIELDS} }} }}"
    )
    ops = json.dumps({"query": q, "variables": {"file": None, "name": name, "method": method}})
    with open(src, "rb") as fh:
        resp = client.post(
            "/graphql",
            data={"operations": ops, "map": json.dumps({"0": ["variables.file"]})},
            files={"0": (f"{name}.csv", fh, "text/csv")},
        )
    body = resp.json()
    assert "errors" not in body, body["errors"]
    return body["data"]["uploadDraftClass"]


def create_league(client, **extra):
    q = (
        "mutation($name: String!, $url: String, $ids: [Int!]) { createLeague("
        'name: $name, leagueUrl: $url, sessionid: "sid", csrftoken: "csrf", '
        f"gameLeagueIds: $ids) {{ {LEAGUE_FIELDS} }} }}"
    )
    return gql(client, q, name=LEAGUE_NAME, url=LEAGUE_URL, ids=[100], **extra)["createLeague"]


def ranked(client, fields="id", **args):
    q = (
        "query($name: String!, $filter: RankedPlayerFilter, $sort: RankedPlayerSort, "
        "$page: Int, $pageSize: Int, $all: Boolean) { rankedPlayers(name: $name, "
        "filter: $filter, sort: $sort, page: $page, pageSize: $pageSize, allRows: $all) "
        f"{{ totalRecords rows {{ {fields} }} }} }}"
    )
    args.setdefault("name", CLASS)
    return gql(client, q, **args)["rankedPlayers"]


BREAKDOWN_FIELDS = """
  playerType
  batting { battingModel runningModel positionModel bestPositionScore utilityBonus
            modifiers { modifiers { name value } total } }
  pitching {
    starter { model baseModifier pitchMix hrRisk score }
    reliever { model baseModifier pitchMix hrRisk score }
    modifiers { modifiers { name value } total }
  }
  rankAdjust { preRank preScore modifiers { name value } }
  legacy { name value }
"""


def breakdowns_by_id(client, page):
    """`playerBreakdown` for every row of a page, keyed by player id, batched as
    aliased fields of one query. Each row carries its own `source`."""
    rows = page["rows"]
    if not rows:
        return {}
    fields = " ".join(
        f'p{i}: playerBreakdown(source: $s{i}, playerId: "{r["id"]}") {{ {BREAKDOWN_FIELDS} }}'
        for i, r in enumerate(rows)
    )
    args = ", ".join(f"$s{i}: RankingSourceInput!" for i in range(len(rows)))
    data = gql(client, f"query({args}) {{ {fields} }}", **{
        f"s{i}": r["source"] for i, r in enumerate(rows)
    })
    return {r["id"]: data[f"p{i}"] for i, r in enumerate(rows)}


def class_breakdowns(client, name=CLASS):
    return breakdowns_by_id(client, ranked(client, "id source { className leagueId method }", name=name, all=True))


# old flat `components` key -> where the typed breakdown keeps that value
_OLD_KEY_PATHS = {
    "Pos - Batting Model": ("batting", "battingModel"),
    "Pos - Running Model": ("batting", "runningModel"),
    "Pos - Overall Model Score": ("batting", "positionModel"),
    "Pos - Best Pos Score (*)": ("batting", "bestPositionScore"),
    "Pos - Utility Bonus": ("batting", "utilityBonus"),
    "Total Pos Modifier": ("batting", "modifiers", "total"),
    "SP Model Score": ("pitching", "starter", "model"),
    "SP Base Modifier": ("pitching", "starter", "baseModifier"),
    "SP Pitcher Pitch Component": ("pitching", "starter", "pitchMix"),
    "SP HR component": ("pitching", "starter", "hrRisk"),
    "Starter Score w/Modifiers": ("pitching", "starter", "score"),
    "RP Model Score": ("pitching", "reliever", "model"),
    "RP Base Modifier": ("pitching", "reliever", "baseModifier"),
    "Reliever Score w/Modifiers": ("pitching", "reliever", "score"),
    "Total Pitcher Modifier": ("pitching", "modifiers", "total"),
    "Pre Rank-adj Rank": ("rankAdjust", "preRank"),
    "Pre Rank-adj Score": ("rankAdjust", "preScore"),
}
_OLD_PREFIXES = (
    ("Pos Modifier ", ("batting", "modifiers", "modifiers")),
    ("Pitcher Modifier ", ("pitching", "modifiers", "modifiers")),
    ("Rank-adj Modifier ", ("rankAdjust", "modifiers")),
)


def _as_old_keys(b):
    """A typed breakdown flattened back to old-style `components` keys."""
    out = {}

    def dig(path):
        node = b
        for key in path:
            node = (node or {}).get(key)
        return node

    for key, path in _OLD_KEY_PATHS.items():
        if dig(path) is not None:
            out[key] = dig(path)
    for prefix, path in _OLD_PREFIXES:
        for item in dig(path) or []:
            if item["value"] is not None:
                out[prefix + item["name"]] = item["value"]
    return out


def _side(old_key):
    if old_key.startswith(("Pos", "Total Pos")):
        return "batting"
    if old_key.startswith(
        ("SP ", "RP ", "Starter", "Reliever", "Pitcher", "Pre-Pitcher", "Total Pitcher")
    ):
        return "pitching"
    return "rank"


def check_breakdowns(golden_name, section, breakdowns, types):
    """Every player's typed breakdown against the old `components` recorded in
    `golden_name` (pre-change, read-only):
      * the side the player isn't judged on is gone,
      * every old value on a relevant side is still there, at its new place,
      * anything new is a value the old code silently dropped (<= 0)."""
    old_all = json.loads((GOLDEN_DIR / f"{golden_name}.json").read_text())[section]
    assert set(breakdowns) == set(old_all), f"{section}: player set changed"
    problems = []
    for pid, b in breakdowns.items():
        ptype = types[pid]
        if b["playerType"] != ptype:
            problems.append(f"{pid}: playerType {b['playerType']} != row type {ptype}")
        if ptype == "Hitter" and b["pitching"] is not None:
            problems.append(f"{pid}: Hitter still has a pitching breakdown")
        if ptype == "Pitcher" and b["batting"] is not None:
            problems.append(f"{pid}: Pitcher still has a batting breakdown")
        relevant = {"rank"} | (
            {"batting"} if ptype in ("Hitter", "Two-way") else set()
        ) | ({"pitching"} if ptype in ("Pitcher", "Two-way") else set())
        old = {
            re.sub(r"\(\w+\)$", "(*)", k): v for k, v in (old_all[pid] or {}).items()
            if _side(k) in relevant
        }
        new = _as_old_keys(b)
        for key, value in old.items():
            if key not in new:
                problems.append(f"{pid}: {key!r} lost (was {value})")
            elif _diff(value, new[key]):
                problems.append(f"{pid}: {key!r} {new[key]} != {value}")
        for key, value in new.items():
            if key not in old and value > 0:
                problems.append(f"{pid}: new {key!r} = {value} (only <= 0 values were dropped)")
    assert not problems, f"{section}: {len(problems)} problem(s):\n" + "\n".join(problems[:40])


def draft_class(client):
    return gql(client, f'{{ draftClass(name: "{CLASS}") {{ {CLASS_FIELDS} }} }}')["draftClass"]


def upload_csv(client):
    resp = client.get(f"/download/{CLASS}/upload.csv")
    assert resp.status_code == 200
    return resp.text.splitlines()


# ----------------------------------------------------------- draft class flow
def test_draft_class_flow(client, tmp_path, monkeypatch):
    out, breakdowns, types = {}, {}, {}
    out["league_created"] = create_league(client)
    league_id = out["league_created"]["id"]
    out["uploaded"] = upload_class(client, tmp_path)
    out["classes"] = gql(client, f"{{ draftClasses {{ {CLASS_FIELDS} }} }}")["draftClasses"]
    out["rows_draft_class"] = ranked(client, PLAYER_FIELDS, all=True)
    breakdowns["draft_class"] = class_breakdowns(client)
    types["draft_class"] = {r["id"]: r["type"] for r in out["rows_draft_class"]["rows"]}

    out["page_pitchers_by_score_asc"] = ranked(
        client, "rank id modelScore", filter={"positions": ["SP", "RP"]},
        sort={"field": "modelScore", "order": 1}, page=1, pageSize=10,
    )
    out["page_numeric_power"] = ranked(
        client, "rank id", filter={"search": "a", "numeric": [{"field": "batting.power", "min": 60}]},
        sort={"field": "batting.power", "order": -1}, all=True,
    )
    out["page_best_pos_hands_demand"] = ranked(
        client, "rank id demand",
        filter={"bestPositions": ["SS", "CF", "C"], "batHands": ["Left", "Switch"]},
        sort={"field": "demandKey", "order": 1}, all=True,
    )
    out["page_work_ethic_desc"] = ranked(
        client, "rank id", sort={"field": "workEthic", "order": -1}, page=0, pageSize=15,
    )
    out["page_slider_desc"] = ranked(
        client, "rank id", filter={"throwHands": ["Left"]},
        sort={"field": "pitch.Slider", "order": -1}, all=True,
    )
    out["positions"] = gql(client, f'{{ classPositions(name: "{CLASS}") }}')["classPositions"]
    out["upload_csv"] = upload_csv(client)

    out["set_league"] = gql(
        client,
        f'mutation {{ setClassLeague(name: "{CLASS}", leagueId: "{league_id}") {{ {CLASS_FIELDS} }} }}',
    )["setClassLeague"]
    out["leagues"] = gql(client, f"{{ leagues {{ {LEAGUE_FIELDS} }} }}")["leagues"]

    picks = e2e_fixtures.draft_picks(e2e_fixtures.make_draft_class_csv())
    seen = {}

    def fake_picks(league_url, cookie, lid=None, timeout=30.0):
        seen.update(league_url=league_url, cookie=cookie, lid=lid)
        return picks

    monkeypatch.setattr("web.service.fetch_draft_picks", fake_picks)
    out["drafted_refresh"] = gql(
        client,
        f'mutation {{ refreshDraftedFromStatsPlus(name: "{CLASS}") '
        "{ draftedCount matchedById matchedByName unmatched } }",
    )["refreshDraftedFromStatsPlus"]
    out["drafted_request"] = seen
    out["after_drafted_class"] = draft_class(client)
    out["draft_teams"] = gql(client, f'{{ draftTeams(name: "{CLASS}") }}')["draftTeams"]
    out["hide_drafted"] = ranked(client, "rank id", filter={"hideDrafted": True}, all=True)
    out["team_filter"] = ranked(
        client, "rank id drafted draftedTeam draftedPick draftedRound draftedRoundPick",
        filter={"teams": ["Brewers", "Armadillos"]}, all=True,
    )
    out["upload_csv_after_drafted"] = upload_csv(client)

    ids = [r["id"] for r in ranked(client, "id", all=True)["rows"]]
    out["set_player_rank"] = gql(
        client,
        f'mutation {{ setPlayerRank(name: "{CLASS}", id: "{ids[20]}", rank: 2) {{ {CLASS_FIELDS} }} }}',
    )["setPlayerRank"]
    out["after_set_rank_top"] = ranked(client, "rank id", page=0, pageSize=25)
    reorder = list(reversed(ids[:6])) + ids[6:]
    out["save_custom_order"] = gql(
        client,
        f'mutation($o: [ID!]!) {{ saveCustomOrder(name: "{CLASS}", order: $o) {{ {CLASS_FIELDS} }} }}',
        o=reorder,
    )["saveCustomOrder"]
    out["after_save_order_top"] = ranked(client, "rank id", page=0, pageSize=25)
    out["upload_csv_custom_order"] = upload_csv(client)
    out["clear_custom_order"] = gql(
        client, f'mutation {{ clearCustomOrder(name: "{CLASS}") {{ {CLASS_FIELDS} }} }}'
    )["clearCustomOrder"]
    out["after_clear_top"] = ranked(client, "rank id", page=0, pageSize=25)

    for method in ("potential", "overall"):
        out[f"set_method_{method}"] = gql(
            client,
            f'mutation {{ setRankingMethod(name: "{CLASS}", rankingMethod: "{method}") '
            f"{{ {CLASS_FIELDS} }} }}",
        )["setRankingMethod"]
        out[f"rows_{method}"] = ranked(client, PLAYER_FIELDS, all=True)
        breakdowns[method] = class_breakdowns(client)
        types[method] = {r["id"]: r["type"] for r in out[f"rows_{method}"]["rows"]}
    out["reprocess"] = gql(
        client, f'mutation {{ reprocessDraftClass(name: "{CLASS}") {{ {CLASS_FIELDS} }} }}'
    )["reprocessDraftClass"]

    out["delete_class"] = gql(client, f'mutation {{ deleteDraftClass(name: "{CLASS}") }}')
    out["classes_after_delete"] = gql(client, "{ draftClasses { name } }")["draftClasses"]
    out["leagues_after_delete"] = gql(client, f"{{ leagues {{ {LEAGUE_FIELDS} }} }}")["leagues"]

    check_golden("draft_class_flow", out)
    for section in breakdowns:
        check_breakdowns("draft_class_components", section, breakdowns[section], types[section])
    check_golden("draft_class_breakdowns", breakdowns)


# --------------------------------------------------------- live league flow
@pytest.fixture
def fake_statsplus(monkeypatch):
    ratings, players, teams = e2e_fixtures.make_statsplus_csvs()
    state = {"date": LEAGUE_DATE, "calls": []}

    def fetch(kind, text):
        def _f(league_url, cookie, *a, **kw):
            state["calls"].append((kind, league_url, cookie))
            return text
        return _f

    def fake_date(league_url, cookie, *a, **kw):
        state["calls"].append(("date", league_url, cookie))
        return state["date"]

    monkeypatch.setattr("league_snapshot.fetch_ratings", fetch("ratings", ratings))
    monkeypatch.setattr("league_snapshot.fetch_players", fetch("players", players))
    monkeypatch.setattr("league_snapshot.fetch_teams", fetch("teams", teams))
    monkeypatch.setattr("league_snapshot.fetch_league_date", fake_date)
    monkeypatch.setattr("web.service.fetch_league_date", fake_date)
    return state


def league_players(client, league_id, method, fields="rank id", **args):
    q = (
        "query($l: ID!, $m: String!, $g: LeagueGroupBy!, $gid: ID, $filter: RankedPlayerFilter, "
        "$sort: RankedPlayerSort, $page: Int, $pageSize: Int, $all: Boolean) { "
        "leagueSnapshotPlayers(leagueId: $l, method: $m, groupBy: $g, groupId: $gid, "
        "filter: $filter, sort: $sort, page: $page, pageSize: $pageSize, allRows: $all) "
        f"{{ totalRecords rows {{ {fields} }} }} }}"
    )
    args.setdefault("g", "LEAGUE")
    return gql(client, q, l=league_id, m=method, **args)["leagueSnapshotPlayers"]


def refresh_and_wait(client, league_id):
    started = gql(
        client,
        f'mutation {{ refreshLeagueSnapshot(leagueId: "{league_id}") {{ {STATUS_FIELDS} }} }}',
    )["refreshLeagueSnapshot"]
    deadline = time.monotonic() + 300
    while True:
        status = gql(
            client, f'{{ leagueRefreshStatus(leagueId: "{league_id}") {{ {STATUS_FIELDS} }} }}'
        )["leagueRefreshStatus"]
        if status["state"] != "running":
            return started, status
        assert time.monotonic() < deadline, "league refresh never finished"
        time.sleep(0.2)


def test_league_flow(client, fake_statsplus, monkeypatch):
    out, breakdowns, types = {}, {}, {}
    league = create_league(client)
    lid = league["id"]
    out["league_created"] = league
    out["snapshot_before"] = gql(
        client, f'{{ leagueSnapshot(leagueId: "{lid}") {{ {SNAPSHOT_FIELDS} }} }}'
    )["leagueSnapshot"]
    out["players_before"] = league_players(client, lid, "overall", all=True)
    out["status_before"] = gql(
        client, f'{{ leagueRefreshStatus(leagueId: "{lid}") {{ {STATUS_FIELDS} }} }}'
    )["leagueRefreshStatus"]

    out["refresh_started"], out["refresh_finished"] = refresh_and_wait(client, lid)
    out["statsplus_calls"] = sorted({c[0] for c in fake_statsplus["calls"]})
    out["snapshot"] = gql(
        client, f'{{ leagueSnapshot(leagueId: "{lid}") {{ {SNAPSHOT_FIELDS} }} }}'
    )["leagueSnapshot"]
    out["leagues"] = gql(client, f"{{ leagues {{ {LEAGUE_FIELDS} }} }}")["leagues"]
    team_fields = "id name parentTeamId level"
    out["orgs"] = gql(client, f'{{ leagueOrgs(leagueId: "{lid}") {{ {team_fields} }} }}')["leagueOrgs"]
    out["teams"] = gql(client, f'{{ leagueTeams(leagueId: "{lid}") {{ {team_fields} }} }}')["leagueTeams"]
    out["levels"] = gql(client, f'{{ leagueLevels(leagueId: "{lid}") }}')["leagueLevels"]
    out["game_leagues"] = gql(
        client,
        f'{{ leagueGameLeagues(leagueId: "{lid}") {{ id orgCount playerCount sampleOrgs }} }}',
    )["leagueGameLeagues"]

    for method in ("overall", "potential"):
        out[f"rows_{method}"] = league_players(client, lid, method, PLAYER_FIELDS, all=True)
        breakdowns[method] = breakdowns_by_id(client, league_players(
            client, lid, method, "id source { className leagueId method }", all=True
        ))
        types[method] = {r["id"]: r["type"] for r in out[f"rows_{method}"]["rows"]}
        out[f"{method}_org_46"] = league_players(client, lid, method, g="ORG", gid="46", all=True)
        out[f"{method}_team_246"] = league_players(client, lid, method, g="TEAM", gid="246", all=True)
        out[f"{method}_org_unpicked"] = league_players(client, lid, method, g="ORG", all=True)
        out[f"{method}_levels_rule5"] = league_players(
            client, lid, method, "rank id level rule5Eligible",
            filter={"levels": ["AA", "A"], "rule5Eligible": True}, all=True,
        )
        out[f"{method}_protected"] = league_players(
            client, lid, method, filter={"rule5Eligible": False}, all=True,
        )
        out[f"{method}_numeric_sorted"] = league_players(
            client, lid, method, "rank id modelScore",
            filter={"numeric": [{"field": "modelScore", "min": 20}]},
            sort={"field": "pitching.stuff", "order": -1}, all=True,
        )
        out[f"{method}_paged_age"] = league_players(
            client, lid, method, "rank id age", filter={"search": "e"},
            sort={"field": "age", "order": 1}, page=1, pageSize=7,
        )

    rankings_q = (
        f'{{ leagueOrgRankings(leagueId: "{lid}") {{ orgId orgName orgScore prospectCount '
        "top10 top50 top100 top250 top500 topProspects { rank id name modelScore level } } }"
    )
    out["org_rankings"] = gql(client, rankings_q)["leagueOrgRankings"]

    fresh_q = (
        f'mutation {{ checkLeagueSnapshotFreshness(leagueId: "{lid}") '
        f"{{ stale checked leagueDate snapshot {{ {SNAPSHOT_FIELDS} }} }} }}"
    )
    out["freshness_recent"] = gql(client, fresh_q)["checkLeagueSnapshotFreshness"]
    monkeypatch.setattr("league_snapshot.STALE_AFTER", timedelta(0))
    out["freshness_same_date"] = gql(client, fresh_q)["checkLeagueSnapshotFreshness"]
    fake_statsplus["date"] = "2042-06-01"
    out["freshness_new_date"] = gql(client, fresh_q)["checkLeagueSnapshotFreshness"]

    out["unscoped"] = gql(
        client,
        f'mutation {{ updateLeague(id: "{lid}", gameLeagueIds: []) {{ {LEAGUE_FIELDS} }} }}',
    )["updateLeague"]
    out["orgs_unscoped"] = gql(client, f'{{ leagueOrgs(leagueId: "{lid}") {{ id name }} }}')["leagueOrgs"]
    out["org_rankings_unscoped"] = [
        r["orgId"] for r in gql(client, rankings_q)["leagueOrgRankings"]
    ]
    out["delete_league"] = gql(client, f'mutation {{ deleteLeague(id: "{lid}") }}')
    out["leagues_after_delete"] = gql(client, "{ leagues { id } }")["leagues"]

    check_golden("league_flow", out)
    for section in breakdowns:
        check_breakdowns("league_components", section, breakdowns[section], types[section])
    check_golden("league_breakdowns", breakdowns)


# ------------------------------------------------- legacy data directory
# A $DATA_DIR written by the pre-SQLite app (commit b6179fa): leagues.json, two
# classes (one with StatsPlus-API drafted picks + a custom order + a league pin,
# one ranked by the overall model with a legacy name-scrape drafted file) and a
# scored league snapshot. Recorded once by tests/record_legacy_fixture.py and
# never regenerated - it stands in for the files on the production volume.
LEGACY_FIXTURE = Path(__file__).parent / "fixtures" / "legacy_data_dir.tar.gz"
LEGACY_CLASSES = ("fx-draft", "fx-overall")
LEGACY_LEAGUE = "golden-fixture-league"


def read_everything(client):
    """Every read-only query over the legacy fixture's contents."""
    out, breakdowns = {}, {}
    out["classes"] = gql(client, f"{{ draftClasses {{ {CLASS_FIELDS} }} }}")["draftClasses"]
    out["leagues"] = gql(client, f"{{ leagues {{ {LEAGUE_FIELDS} }} }}")["leagues"]
    for name in LEGACY_CLASSES:
        out[f"{name}_rows"] = ranked(client, PLAYER_FIELDS, name=name, all=True)
        breakdowns[name] = class_breakdowns(client, name)
        out[f"{name}_teams"] = gql(client, f'{{ draftTeams(name: "{name}") }}')["draftTeams"]
        resp = client.get(f"/download/{name}/upload.csv")
        out[f"{name}_upload_csv"] = [resp.status_code] + resp.text.splitlines()
    lid = LEGACY_LEAGUE
    out["snapshot"] = gql(
        client, f'{{ leagueSnapshot(leagueId: "{lid}") {{ {SNAPSHOT_FIELDS} }} }}'
    )["leagueSnapshot"]
    out["status"] = gql(
        client, f'{{ leagueRefreshStatus(leagueId: "{lid}") {{ {STATUS_FIELDS} }} }}'
    )["leagueRefreshStatus"]
    out["orgs"] = gql(client, f'{{ leagueOrgs(leagueId: "{lid}") {{ id name }} }}')["leagueOrgs"]
    out["teams"] = gql(
        client, f'{{ leagueTeams(leagueId: "{lid}") {{ id name parentTeamId level }} }}'
    )["leagueTeams"]
    out["levels"] = gql(client, f'{{ leagueLevels(leagueId: "{lid}") }}')["leagueLevels"]
    out["game_leagues"] = gql(
        client, f'{{ leagueGameLeagues(leagueId: "{lid}") {{ id orgCount playerCount }} }}'
    )["leagueGameLeagues"]
    for method in ("overall", "potential"):
        out[f"league_{method}"] = league_players(client, lid, method, PLAYER_FIELDS, all=True)
        breakdowns[f"league_{method}"] = breakdowns_by_id(client, league_players(
            client, lid, method, "id source { className leagueId method }", all=True
        ))
    out["org_rankings"] = gql(
        client,
        f'{{ leagueOrgRankings(leagueId: "{lid}") {{ orgId orgScore prospectCount '
        "topProspects { id } } }",
    )["leagueOrgRankings"]
    return out, breakdowns


def test_legacy_data_dir(client, data_dir):
    """The importer turns a pre-SQLite volume into the same API output - the old
    ranked CSVs come in as stored runs, nothing is re-scored."""
    import tarfile

    with tarfile.open(LEGACY_FIXTURE) as tar:
        tar.extractall(data_dir)
    out, breakdowns = read_everything(client)
    check_golden("legacy_data_dir", out)
    for section, by_id in breakdowns.items():
        rows = out[f"{section}_rows" if not section.startswith("league_") else section]["rows"]
        check_breakdowns(
            "legacy_data_dir_components", section, by_id, {r["id"]: r["type"] for r in rows}
        )
        assert all(not b["legacy"] for b in by_id.values())
    check_golden("legacy_data_dir_breakdowns", breakdowns)


# ------------------------------------------------------------------ CLI
def run_cli(capsys, monkeypatch, script, *argv):
    monkeypatch.setattr(sys, "argv", [script, *argv])
    capsys.readouterr()
    runpy.run_path(str(Path(__file__).parent.parent / script), run_name="__main__")
    return capsys.readouterr().out.splitlines()


def test_cli_output(client, tmp_path, monkeypatch, capsys):
    import constants

    upload_class(client, tmp_path)
    picks = e2e_fixtures.draft_picks(e2e_fixtures.make_draft_class_csv())
    monkeypatch.setattr("web.service.fetch_draft_picks", lambda *a, **kw: picks)
    league_id = create_league(client)["id"]
    gql(client, f'mutation {{ setClassLeague(name: "{CLASS}", leagueId: "{league_id}") {{ name }} }}')
    gql(client, f'mutation {{ refreshDraftedFromStatsPlus(name: "{CLASS}") {{ draftedCount }} }}')
    monkeypatch.setattr(constants, "DRAFT_CLASS_NAME", CLASS)

    out = {}
    out["evals_top25"] = run_cli(capsys, monkeypatch, "print_evals.py", "-t", "25")
    out["evals_pitchers_with_drafted"] = run_cli(
        capsys, monkeypatch, "print_evals.py", "-t", "10", "-a", "-p", "pit")
    out["evals_drafted_only"] = run_cli(capsys, monkeypatch, "print_evals.py", "-d", "-t", "50")
    out["evals_minimal_by_potential"] = run_cli(
        capsys, monkeypatch, "print_evals.py", "-m", "-s", "-t", "15")
    out["pos_distribution"] = run_cli(capsys, monkeypatch, "print_pos_distribution.py", "-t", "40")
    out["org_summaries"] = run_cli(capsys, monkeypatch, "print_org_summaries.py")
    out["org_detail"] = run_cli(capsys, monkeypatch, "print_org_summaries.py", "-o", "-", "-t", "8")

    from context import DraftClassContext
    from ranking_csv import write_upload_file

    ctx = DraftClassContext(CLASS)
    write_upload_file(ctx)
    out["upload_file"] = ctx.upload_players_file.read_text().splitlines()

    out["update_config"] = run_cli(capsys, monkeypatch, "update_config.py", "-r", "potential")
    from pipeline import process_class

    process_class(ctx)
    capsys.readouterr()
    out["evals_potential"] = run_cli(capsys, monkeypatch, "print_evals.py", "-t", "12")

    check_golden("cli_output", out)
