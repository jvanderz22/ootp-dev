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


def test_settings_update(client):
    out = gql(
        client,
        'mutation { updateStatsPlusSettings(leagueUrl: "https://statsplus.net/yfmlb/", '
        'sessionid: "abc", csrftoken: "def") '
        "{ leagueUrl hasSessionid hasCsrftoken } }",
    )["updateStatsPlusSettings"]
    assert out == {
        "leagueUrl": "https://statsplus.net/yfmlb/",
        "hasSessionid": True,
        "hasCsrftoken": True,
    }
    # the values themselves are never exposed
    again = gql(
        client, "{ statsPlusSettings { leagueUrl hasSessionid hasCsrftoken } }"
    )["statsPlusSettings"]
    assert again["hasSessionid"] and again["hasCsrftoken"]


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


def test_settings_accepts_bare_slug_and_alt_host(client):
    out = gql(
        client,
        'mutation { updateStatsPlusSettings(leagueUrl: "yfmlb") { leagueUrl } }',
    )["updateStatsPlusSettings"]
    assert out["leagueUrl"] == "https://statsplus.net/yfmlb/"

    out = gql(
        client,
        'mutation { updateStatsPlusSettings(leagueUrl: "atl-01.statsplus.net/wbf") { leagueUrl } }',
    )["updateStatsPlusSettings"]
    assert out["leagueUrl"] == "https://atl-01.statsplus.net/wbf/"


def test_settings_rejects_foreign_host(client):
    resp = client.post(
        "/graphql",
        json={
            "query": 'mutation { updateStatsPlusSettings(leagueUrl: "https://evil.example/x") { leagueUrl } }'
        },
    )
    body = resp.json()
    assert "errors" in body
    assert "statsplus.net" in body["errors"][0]["message"]
