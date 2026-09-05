import json

import pytest

pytestmark = pytest.mark.slow


@pytest.fixture
def client(data_dir, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")  # disable auth for these tests
    from starlette.testclient import TestClient

    from web.app import app

    return TestClient(app)


def gql(client, query, **variables):
    resp = client.post("/graphql", json={"query": query, "variables": variables})
    resp.raise_for_status()
    body = resp.json()
    assert "errors" not in body, body["errors"]
    return body["data"]


def test_schema_parses():
    from web.schema import schema  # noqa: F401  - raises if SDL is invalid


def test_empty_draft_classes(client):
    assert gql(client, "{ draftClasses { name } }")["draftClasses"] == []


def test_upload_then_query_then_reorder(client):
    from tests.conftest import SAMPLE_DATASET

    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset not present")

    q = (
        "mutation($file: Upload!) { uploadDraftClass("
        'name: "g", rankingMethod: "draft_class", file: $file) '
        "{ name playerCount rankingMethod } }"
    )
    ops = json.dumps({"query": q, "variables": {"file": None}})
    with open(SAMPLE_DATASET, "rb") as fh:
        resp = client.post(
            "/graphql",
            data={"operations": ops, "map": json.dumps({"0": ["variables.file"]})},
            files={"0": ("g.csv", fh, "text/csv")},
        )
    body = resp.json()
    assert "errors" not in body, body["errors"]
    assert body["data"]["uploadDraftClass"]["playerCount"] > 100

    def ranked_ids(**vars):
        q = (
            "query($all: Boolean) { rankedPlayers(name: \"g\", allRows: $all) "
            "{ totalRecords rows { rank id modelScore drafted } } }"
        )
        return gql(client, q, **vars)["rankedPlayers"]

    page = ranked_ids(all=True)
    players = page["rows"]
    assert page["totalRecords"] == len(players)
    assert players[0]["rank"] == 1
    ids = [p["id"] for p in players]

    reordered = [ids[2]] + ids[:2] + ids[3:]
    saved = gql(
        client,
        "mutation($o: [ID!]!) { saveCustomOrder(name: \"g\", order: $o) { hasCustomOrder } }",
        o=reordered,
    )["saveCustomOrder"]
    assert saved["hasCustomOrder"] is True
    assert [r["id"] for r in ranked_ids(all=True)["rows"][:3]] == [ids[2], ids[0], ids[1]]

    dl = client.get("/download/g/upload.csv")
    assert dl.status_code == 200
    assert dl.text.splitlines()[0].split(",")[0] == ids[2]

    reverted = gql(client, 'mutation { clearCustomOrder(name: "g") { hasCustomOrder } }')[
        "clearCustomOrder"
    ]
    assert reverted["hasCustomOrder"] is False
    assert [r["id"] for r in ranked_ids(all=True)["rows"][:3]] == ids[:3]


def test_handedness_filters(client):
    from tests.conftest import SAMPLE_DATASET

    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset not present")

    q = (
        "mutation($file: Upload!) { uploadDraftClass("
        'name: "h", rankingMethod: "draft_class", file: $file) { name } }'
    )
    ops = json.dumps({"query": q, "variables": {"file": None}})
    with open(SAMPLE_DATASET, "rb") as fh:
        resp = client.post(
            "/graphql",
            data={"operations": ops, "map": json.dumps({"0": ["variables.file"]})},
            files={"0": ("h.csv", fh, "text/csv")},
        )
    assert "errors" not in resp.json(), resp.json()

    def rows(**filt):
        q = (
            "query($f: RankedPlayerFilter) { rankedPlayers(name: \"h\", filter: $f, "
            "allRows: true) { totalRecords rows { batHand throwHand } } }"
        )
        return gql(client, q, f=filt)["rankedPlayers"]

    everyone = rows()
    total = everyone["totalRecords"]
    assert total > 100

    lefty_bats = rows(batHands=["Left"])
    assert 0 < lefty_bats["totalRecords"] < total
    assert {r["batHand"] for r in lefty_bats["rows"]} == {"Left"}

    righty_throws = rows(throwHands=["Right"])
    assert {r["throwHand"] for r in righty_throws["rows"]} == {"Right"}

    # both filters AND together
    combo = rows(batHands=["Left", "Switch"], throwHands=["Right"])
    assert all(
        r["batHand"] in {"Left", "Switch"} and r["throwHand"] == "Right"
        for r in combo["rows"]
    )
    assert combo["totalRecords"] <= righty_throws["totalRecords"]


def test_draft_pick_columns_and_team_filter(client):
    from context import DraftClassContext
    from statsplus_api import _parse_draft_csv, write_drafted_players_file
    from tests.conftest import SAMPLE_DATASET
    from tests.test_statsplus_api import DRAFTV2_CSV

    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset not present")

    q = (
        "mutation($file: Upload!) { uploadDraftClass("
        'name: "d", rankingMethod: "draft_class", file: $file) { name } }'
    )
    ops = json.dumps({"query": q, "variables": {"file": None}})
    with open(SAMPLE_DATASET, "rb") as fh:
        resp = client.post(
            "/graphql",
            data={"operations": ops, "map": json.dumps({"0": ["variables.file"]})},
            files={"0": ("d.csv", fh, "text/csv")},
        )
    assert "errors" not in resp.json(), resp.json()

    # Mark a player that's known to be in the sample dataset as drafted.
    write_drafted_players_file(DraftClassContext("d"), _parse_draft_csv(DRAFTV2_CSV))

    assert gql(client, 'query { draftTeams(name: "d") }')["draftTeams"] == ["Expos"]

    def rows(**filt):
        query = (
            'query($f: RankedPlayerFilter) { rankedPlayers(name: "d", filter: $f, '
            "allRows: true) { totalRecords rows { id drafted draftedTeam "
            "draftedPick draftedRound draftedRoundPick } } }"
        )
        return gql(client, query, f=filt)["rankedPlayers"]

    drafted = [r for r in rows()["rows"] if r["drafted"]]
    assert len(drafted) == 1
    assert drafted[0] == {
        "id": "76230",
        "drafted": True,
        "draftedTeam": "Expos",
        "draftedPick": 1,
        "draftedRound": 1,
        "draftedRoundPick": 1,
    }

    only = rows(teams=["Expos"])
    assert only["totalRecords"] == 1 and only["rows"][0]["id"] == "76230"

    # the Pick column is filterable through the generic numeric path
    assert rows(numeric=[{"field": "draftedPick", "min": 2}])["totalRecords"] == 0


def test_settings_update(client):
    out = gql(
        client,
        'mutation { updateStatsPlusSettings(sessionid: "abc", csrftoken: "def") '
        "{ hasSessionid hasCsrftoken } }",
    )["updateStatsPlusSettings"]
    assert out == {"hasSessionid": True, "hasCsrftoken": True}
    # the values themselves are never exposed
    again = gql(
        client, "{ statsPlusSettings { hasSessionid hasCsrftoken } }"
    )["statsPlusSettings"]
    assert again["hasSessionid"] and again["hasCsrftoken"]


def test_league_crud_and_class_assignment(client):
    made = gql(
        client,
        'mutation { createLeague(name: "YF MLB", leagueUrl: "yfmlb", defaultLid: 12) '
        "{ id name leagueUrl defaultLid classNames } }",
    )["createLeague"]
    assert made["name"] == "YF MLB"
    assert made["leagueUrl"] == "https://statsplus.net/yfmlb/"
    assert made["defaultLid"] == 12
    assert made["classNames"] == []
    league_id = made["id"]

    listed = gql(client, "{ leagues { id name } }")["leagues"]
    assert [lg["id"] for lg in listed] == [league_id]

    gone = gql(
        client, f'mutation {{ deleteLeague(id: "{league_id}") }}'
    )["deleteLeague"]
    assert gone == league_id
    assert gql(client, "{ leagues { id } }")["leagues"] == []


def test_create_league_rejects_foreign_host(client):
    resp = client.post(
        "/graphql",
        json={
            "query": 'mutation { createLeague(name: "x", leagueUrl: "https://evil.example/x") { id } }'
        },
    )
    body = resp.json()
    assert "errors" in body
    assert "statsplus.net" in body["errors"][0]["message"]


def test_settings_accepts_name_prefixed_paste(client):
    # each field pulls out just its own value, whether you paste `name=value`,
    # a bare value, or a whole cookie blob
    gql(
        client,
        'mutation { updateStatsPlusSettings('
        'sessionid: "sessionid=xyz; csrftoken=qrs", csrftoken: "  qrs ; ") '
        "{ hasSessionid hasCsrftoken } }",
    )
    from web.settings import cookie_header, load_settings

    assert cookie_header(load_settings()) == "sessionid=xyz; csrftoken=qrs"


def _seed_snapshot(league_id="yf"):
    """Build a stored snapshot under the test DATA_DIR without hitting StatsPlus."""
    from league_snapshot import LeagueSnapshotContext, build_snapshot
    from tests.test_league_snapshot import make_snapshot_csvs

    ctx = LeagueSnapshotContext(league_id)
    build_snapshot(ctx, *make_snapshot_csvs())
    return ctx


def test_league_snapshot_queries(client):
    made = gql(
        client,
        'mutation { createLeague(name: "YF", leagueUrl: "yfmlb") { id } }',
    )["createLeague"]
    lid = made["id"]
    _seed_snapshot(lid)

    snap = gql(
        client,
        'query($l: ID!) { leagueSnapshot(leagueId: $l) { leagueId fetchedAt playerCount } }',
        l=lid,
    )["leagueSnapshot"]
    assert snap["leagueId"] == lid
    assert snap["playerCount"] == 2
    assert snap["fetchedAt"]

    orgs = gql(client, 'query($l: ID!) { leagueOrgs(leagueId: $l) { id name parentTeamId } }', l=lid)[
        "leagueOrgs"
    ]
    assert {o["name"] for o in orgs} == {"Milwaukee Brewers", "Pittsburgh Pirates"}
    assert all(o["parentTeamId"] is None for o in orgs)

    teams = gql(client, 'query($l: ID!) { leagueTeams(leagueId: $l) { id name parentTeamId } }', l=lid)[
        "leagueTeams"
    ]
    assert {t["name"] for t in teams} == {
        "Milwaukee Brewers", "Pittsburgh Pirates", "Indianapolis Indians",
    }
    indy = next(t for t in teams if t["id"] == "168")
    assert indy["parentTeamId"] == "52"

    def players(method, **kw):
        q = (
            "query($l: ID!, $m: String!, $g: LeagueGroupBy!, $gid: ID) {"
            " leagueSnapshotPlayers(leagueId: $l, method: $m, groupBy: $g, groupId: $gid,"
            " allRows: true) { totalRecords rows { id name rank type modelScore drafted draftedTeam } } }"
        )
        return gql(client, q, l=lid, m=method, g=kw.get("g", "LEAGUE"), gid=kw.get("gid"))[
            "leagueSnapshotPlayers"
        ]

    whole_overall = players("overall")
    assert whole_overall["totalRecords"] == 2
    assert {r["id"] for r in whole_overall["rows"]} == {"100", "200"}
    assert [r["rank"] for r in whole_overall["rows"]] == [1, 2]
    assert all(r["drafted"] is False and r["draftedTeam"] is None for r in whole_overall["rows"])

    whole_potential = players("potential")
    assert whole_potential["totalRecords"] == 2
    # the two methods can order the two players differently or the same; both must score
    assert all(r["modelScore"] is not None for r in whole_potential["rows"])

    by_org = players("overall", g="ORG", gid="52")
    assert [r["id"] for r in by_org["rows"]] == ["200"]

    by_team = players("overall", g="TEAM", gid="46")
    assert [r["id"] for r in by_team["rows"]] == ["100"]

    empty = players("overall", g="ORG", gid="999")
    assert empty["totalRecords"] == 0


def test_league_snapshot_players_rejects_bad_method(client):
    lid = gql(client, 'mutation { createLeague(name: "YF2", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]
    _seed_snapshot(lid)
    resp = client.post(
        "/graphql",
        json={
            "query": "query($l: ID!) { leagueSnapshotPlayers(leagueId: $l, method: "
            '"draft_class", groupBy: LEAGUE) { totalRecords } }',
            "variables": {"l": lid},
        },
    )
    body = resp.json()
    assert "errors" in body
    assert "draft_class" in body["errors"][0]["message"]


def test_refresh_league_snapshot(client, monkeypatch):
    import league_snapshot

    lid = gql(client, 'mutation { createLeague(name: "YF3", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]

    from tests.test_league_snapshot import make_snapshot_csvs

    calls = {}

    def fake_fetch_and_build(league, *, base_dir=None, cookie=None):
        calls["league_id"] = league["id"]
        calls["cookie"] = cookie
        ctx = league_snapshot.LeagueSnapshotContext(league["id"])
        return league_snapshot.build_snapshot(ctx, *make_snapshot_csvs())

    monkeypatch.setattr(league_snapshot, "fetch_and_build", fake_fetch_and_build)

    out = gql(
        client,
        'mutation($l: ID!) { refreshLeagueSnapshot(leagueId: $l) { leagueId playerCount } }',
        l=lid,
    )["refreshLeagueSnapshot"]
    assert out == {"leagueId": lid, "playerCount": 2}
    assert calls["league_id"] == lid


def test_league_accepts_bare_slug_and_alt_host(client):
    out = gql(
        client,
        'mutation { createLeague(name: "a", leagueUrl: "yfmlb") { leagueUrl } }',
    )["createLeague"]
    assert out["leagueUrl"] == "https://statsplus.net/yfmlb/"

    out = gql(
        client,
        'mutation { createLeague(name: "b", leagueUrl: "atl-01.statsplus.net/wbf") { leagueUrl } }',
    )["createLeague"]
    assert out["leagueUrl"] == "https://atl-01.statsplus.net/wbf/"
