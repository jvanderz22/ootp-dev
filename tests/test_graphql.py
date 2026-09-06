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


def test_league_cookie_is_per_league_and_never_exposed(client):
    made = gql(
        client,
        'mutation { createLeague(name: "Ck", leagueUrl: "yfmlb", '
        'sessionid: "abc", csrftoken: "def") { id hasSessionid hasCsrftoken } }',
    )["createLeague"]
    assert made["hasSessionid"] is True and made["hasCsrftoken"] is True
    lid = made["id"]

    # the values themselves are never in the schema
    listed = gql(client, "{ leagues { hasSessionid hasCsrftoken } }")["leagues"][0]
    assert listed == {"hasSessionid": True, "hasCsrftoken": True}

    from web import leagues

    assert leagues.get_league(lid)["sessionid"] == "abc"

    # a blank value on update keeps what's stored; a non-blank one replaces it
    gql(
        client,
        f'mutation {{ updateLeague(id: "{lid}", csrftoken: "ghi") '
        "{ hasSessionid hasCsrftoken } }",
    )
    stored = leagues.get_league(lid)
    assert stored["sessionid"] == "abc" and stored["csrftoken"] == "ghi"


def test_class_league_is_explicit_only(client):
    from tests.conftest import SAMPLE_DATASET

    if not SAMPLE_DATASET.exists():
        pytest.skip("sample dataset not present")

    lid = gql(client, 'mutation { createLeague(name: "Solo", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]

    q = (
        "mutation($file: Upload!) { uploadDraftClass("
        'name: "u", rankingMethod: "draft_class", file: $file) { name leagueId leagueName } }'
    )
    ops = json.dumps({"query": q, "variables": {"file": None}})
    with open(SAMPLE_DATASET, "rb") as fh:
        resp = client.post(
            "/graphql",
            data={"operations": ops, "map": json.dumps({"0": ["variables.file"]})},
            files={"0": ("u.csv", fh, "text/csv")},
        )
    body = resp.json()
    assert "errors" not in body, body["errors"]
    # one league exists, but the class was not assigned -> no fallback mapping
    assert body["data"]["uploadDraftClass"]["leagueId"] is None
    assert gql(client, "{ leagues { classNames } }")["leagues"][0]["classNames"] == []

    assigned = gql(
        client, f'mutation {{ setClassLeague(name: "u", leagueId: "{lid}") {{ leagueId leagueName }} }}'
    )["setClassLeague"]
    assert assigned == {"leagueId": lid, "leagueName": "Solo"}
    assert gql(client, "{ leagues { classNames } }")["leagues"][0]["classNames"] == ["u"]


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


def test_league_cookie_accepts_name_prefixed_paste(client):
    # each field pulls out just its own value, whether you paste `name=value`,
    # a bare value, or a whole cookie blob
    lid = gql(
        client,
        'mutation { createLeague(name: "Paste", leagueUrl: "yfmlb", '
        'sessionid: "sessionid=xyz; csrftoken=qrs", csrftoken: "  qrs ; ") { id } }',
    )["createLeague"]["id"]

    from web import leagues
    from web.settings import cookie_header

    assert cookie_header(leagues.get_league(lid)) == "sessionid=xyz; csrftoken=qrs"


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

    snap_q = (
        "query($l: ID!) { leagueSnapshot(leagueId: $l) "
        "{ leagueId fetchedAt playerCount rankedMethods } }"
    )
    snap = gql(client, snap_q, l=lid)["leagueSnapshot"]
    assert snap["leagueId"] == lid
    assert snap["playerCount"] == 2
    assert snap["fetchedAt"]
    assert snap["rankedMethods"] == []  # nothing scored to disk yet

    # pickers only offer clubs that actually roster a player in the snapshot
    orgs = gql(client, 'query($l: ID!) { leagueOrgs(leagueId: $l) { id name parentTeamId } }', l=lid)[
        "leagueOrgs"
    ]
    assert {o["name"] for o in orgs} == {"Milwaukee Brewers", "Pittsburgh Pirates"}
    assert all(o["parentTeamId"] is None for o in orgs)

    teams = gql(
        client,
        'query($l: ID!) { leagueTeams(leagueId: $l) { id name parentTeamId level } }',
        l=lid,
    )["leagueTeams"]
    # id 100 rosters on team 46, id 200 on affiliate 168 -> parent club 52 has
    # no direct roster, so it's absent from the team picker
    assert {t["name"] for t in teams} == {"Milwaukee Brewers", "Indianapolis Indians"}
    indy = next(t for t in teams if t["id"] == "168")
    assert indy["parentTeamId"] == "52"
    # each roster team is tagged with its level, and the list is ordered MLB-first
    assert [(t["name"], t["level"]) for t in teams] == [
        ("Milwaukee Brewers", "MLB"),
        ("Indianapolis Indians", "A"),
    ]

    # the level filter's option set: distinct levels in the snapshot, MLB-first
    levels = gql(client, 'query($l: ID!) { leagueLevels(leagueId: $l) }', l=lid)["leagueLevels"]
    assert levels == ["MLB", "A"]

    def players(method, **kw):
        q = (
            "query($l: ID!, $m: String!, $g: LeagueGroupBy!, $gid: ID) {"
            " leagueSnapshotPlayers(leagueId: $l, method: $m, groupBy: $g, groupId: $gid,"
            " allRows: true) { totalRecords rows { id name rank type modelScore drafted"
            " draftedTeam org team level } } }"
        )
        return gql(client, q, l=lid, m=method, g=kw.get("g", "LEAGUE"), gid=kw.get("gid"))[
            "leagueSnapshotPlayers"
        ]

    whole_overall = players("overall")
    assert whole_overall["totalRecords"] == 2
    assert {r["id"] for r in whole_overall["rows"]} == {"100", "200"}
    assert [r["rank"] for r in whole_overall["rows"]] == [1, 2]
    assert all(r["drafted"] is False and r["draftedTeam"] is None for r in whole_overall["rows"])

    by_id = {r["id"]: r for r in whole_overall["rows"]}
    assert by_id["100"]["org"] == "Milwaukee Brewers"
    assert by_id["100"]["team"] == "Milwaukee Brewers"
    assert by_id["100"]["level"] == "MLB"
    assert by_id["200"]["org"] == "Pittsburgh Pirates"
    assert by_id["200"]["team"] == "Indianapolis Indians"
    assert by_id["200"]["level"] == "A"

    whole_potential = players("potential")
    assert whole_potential["totalRecords"] == 2
    # the two methods can order the two players differently or the same; both must score
    assert all(r["modelScore"] is not None for r in whole_potential["rows"])

    # scoring a method writes ranked_players.csv -> it now reports as ready
    ready = gql(client, snap_q, l=lid)["leagueSnapshot"]["rankedMethods"]
    assert set(ready) == {"overall", "potential"}

    by_org = players("overall", g="ORG", gid="52")
    assert [r["id"] for r in by_org["rows"]] == ["200"]

    by_team = players("overall", g="TEAM", gid="46")
    assert [r["id"] for r in by_team["rows"]] == ["100"]

    empty = players("overall", g="ORG", gid="999")
    assert empty["totalRecords"] == 0

    # level filter narrows the whole-league pool to the chosen playing levels
    lvl_q = (
        "query($l: ID!, $lv: [String!]) { leagueSnapshotPlayers(leagueId: $l,"
        ' method: "overall", groupBy: LEAGUE, filter: { levels: $lv }, allRows: true)'
        " { totalRecords rows { id level } } }"
    )
    only_a = gql(client, lvl_q, l=lid, lv=["A"])["leagueSnapshotPlayers"]
    assert [r["id"] for r in only_a["rows"]] == ["200"]
    both = gql(client, lvl_q, l=lid, lv=["MLB", "A"])["leagueSnapshotPlayers"]
    assert {r["id"] for r in both["rows"]} == {"100", "200"}


def test_league_players_no_selection_is_empty_and_skips_scoring(client):
    lid = gql(client, 'mutation { createLeague(name: "YFn", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]
    _seed_snapshot(lid)
    q = (
        "query($l: ID!) { leagueSnapshotPlayers(leagueId: $l, method: \"overall\","
        " groupBy: ORG) { totalRecords rows { id } } }"
    )
    page = gql(client, q, l=lid)["leagueSnapshotPlayers"]
    assert page == {"totalRecords": 0, "rows": []}
    # and it didn't run the model just to return nothing
    ready = gql(
        client,
        'query($l: ID!) { leagueSnapshot(leagueId: $l) { rankedMethods } }',
        l=lid,
    )["leagueSnapshot"]["rankedMethods"]
    assert ready == []


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


def _await_refresh(client, lid, *, timeout=5.0):
    """Poll leagueRefreshStatus until the background thread finishes."""
    import time

    status_q = (
        "query($l: ID!) { leagueRefreshStatus(leagueId: $l) "
        "{ state error snapshot { playerCount } } }"
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = gql(client, status_q, l=lid)["leagueRefreshStatus"]
        if st["state"] != "running":
            return st
        time.sleep(0.05)
    raise AssertionError(f"refresh for {lid!r} never finished: {st}")


def test_refresh_league_snapshot(client, monkeypatch):
    import league_snapshot

    lid = gql(
        client,
        'mutation { createLeague(name: "YF3", leagueUrl: "yfmlb", '
        'sessionid: "s", csrftoken: "c") { id } }',
    )["createLeague"]["id"]

    from tests.test_league_snapshot import make_snapshot_csvs

    calls = {}

    def fake_fetch_and_build(league, *, base_dir=None, cookie=None, on_phase=None):
        calls["league_id"] = league["id"]
        calls["cookie"] = cookie
        ctx = league_snapshot.LeagueSnapshotContext(league["id"])
        return league_snapshot.build_snapshot(ctx, *make_snapshot_csvs())

    monkeypatch.setattr(league_snapshot, "fetch_and_build", fake_fetch_and_build)

    # the mutation only kicks the job off - it comes back straight away
    started = gql(
        client,
        'mutation($l: ID!) { refreshLeagueSnapshot(leagueId: $l) { leagueId state } }',
        l=lid,
    )["refreshLeagueSnapshot"]
    assert started["leagueId"] == lid
    assert started["state"] in ("running", "done")

    done = _await_refresh(client, lid)
    assert done["state"] == "done"
    assert done["error"] is None
    assert done["snapshot"]["playerCount"] == 2
    assert calls["league_id"] == lid


def test_league_refresh_status_idle_then_error(client, monkeypatch):
    from web import service

    lid = gql(client, 'mutation { createLeague(name: "YF3b", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]

    status_q = "query($l: ID!) { leagueRefreshStatus(leagueId: $l) { state error } }"
    assert gql(client, status_q, l=lid)["leagueRefreshStatus"]["state"] == "idle"

    def boom(_league_id):
        raise service.StatsPlusError("statsplus is down")

    monkeypatch.setattr(service, "_refresh_league_snapshot_sync", boom)

    gql(client, 'mutation($l: ID!) { refreshLeagueSnapshot(leagueId: $l) { state } }', l=lid)
    done = _await_refresh(client, lid)
    assert done["state"] == "error"
    assert "statsplus is down" in done["error"]


def test_check_league_snapshot_freshness(client, monkeypatch):
    import json as _json

    import league_snapshot
    from web import service

    lid = gql(
        client,
        'mutation { createLeague(name: "YF4", leagueUrl: "yfmlb", '
        'sessionid: "s", csrftoken: "c") { id } }',
    )["createLeague"]["id"]
    ctx = _seed_snapshot(lid)

    check = "mutation($l: ID!) { checkLeagueSnapshotFreshness(leagueId: $l) { stale checked leagueDate snapshot { playerCount } } }"

    # 1. just-built snapshot -> under a day old, no external date call
    out = gql(client, check, l=lid)["checkLeagueSnapshotFreshness"]
    assert out == {"stale": False, "checked": False, "leagueDate": None,
                   "snapshot": {"playerCount": 2}}

    dates = iter(["2042-05-19", "2042-06-02"])
    monkeypatch.setattr(service, "fetch_league_date", lambda *a, **k: next(dates))

    def age_snapshot(league_date):
        meta = ctx.load_meta()
        meta["fetched_at"] = "2000-01-01T00:00:00+00:00"
        meta["last_checked_at"] = "2000-01-01T00:00:00+00:00"
        meta["league_date"] = league_date
        ctx.meta_file.write_text(_json.dumps(meta))

    # 2. old snapshot, sim date unchanged -> checked, not stale, and the check
    #    stamps last_checked_at so it goes quiet again
    age_snapshot("2042-05-19")
    out = gql(client, check, l=lid)["checkLeagueSnapshotFreshness"]
    assert out["checked"] is True and out["stale"] is False
    assert out["leagueDate"] == "2042-05-19"
    assert ctx.load_meta()["last_checked_at"] > "2001"

    # 3. old snapshot, sim advanced -> stale (page will auto-refresh)
    age_snapshot("2042-05-19")
    out = gql(client, check, l=lid)["checkLeagueSnapshotFreshness"]
    assert out["checked"] is True and out["stale"] is True
    assert out["leagueDate"] == "2042-06-02"


def test_check_freshness_no_snapshot(client):
    lid = gql(client, 'mutation { createLeague(name: "YF5", leagueUrl: "yfmlb") { id } }')[
        "createLeague"
    ]["id"]
    out = gql(
        client,
        "mutation($l: ID!) { checkLeagueSnapshotFreshness(leagueId: $l) { stale checked snapshot { playerCount } } }",
        l=lid,
    )["checkLeagueSnapshotFreshness"]
    assert out == {"stale": False, "checked": False, "snapshot": None}


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
