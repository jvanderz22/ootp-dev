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
