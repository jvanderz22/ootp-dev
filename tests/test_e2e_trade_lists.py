"""End-to-end golden tests for trade lists, driven only through GraphQL.

The goldens were recorded by running this same file against the pre-SQLite app
(commit b6179fa plus the trade-list commit affa7c1, which stored lists in
`$DATA_DIR/trade_lists.json`), so they pin what users saw before the lists moved
into app.db. `tests/fixtures/legacy_trade_lists.json` stands in for the file on
the production volume.

    UPDATE_GOLDEN=1 python3 -m pytest tests/test_e2e_trade_lists.py
"""
import shutil
import tarfile
from pathlib import Path

import pytest

from tests.test_e2e_golden import (
    LEGACY_FIXTURE,
    LEGACY_LEAGUE,
    PLAYER_FIELDS,
    check_golden,
    client,  # noqa: F401 - fixture
    create_league,
    gql,
)

pytestmark = pytest.mark.slow

LEGACY_TRADE_LISTS = Path(__file__).parent / "fixtures" / "legacy_trade_lists.json"
LIST_FIELDS = "id name entryCount entryIds createdAt"
ROW_FIELDS = PLAYER_FIELDS + " note priority stale"


def gql_error(client, query, **variables):
    body = client.post("/graphql", json={"query": query, "variables": variables}).json()
    assert body.get("errors"), f"expected an error, got {body}"
    err = body["errors"][0]
    return {"message": err["message"], "code": (err.get("extensions") or {}).get("code")}


def trade_lists(client, lid=LEGACY_LEAGUE):
    return gql(client, f'{{ tradeLists(leagueId: "{lid}") {{ {LIST_FIELDS} }} }}')["tradeLists"]


def list_players(client, list_id, lid=LEGACY_LEAGUE):
    return gql(
        client,
        f'{{ tradeListPlayers(leagueId: "{lid}", listId: "{list_id}") '
        f"{{ totalRecords rows {{ {ROW_FIELDS} }} }} }}",
    )["tradeListPlayers"]


def mutate(client, field, args, fields=LIST_FIELDS):
    selection = f" {{ {fields} }}" if fields else ""
    return gql(client, f"mutation {{ {field}({args}){selection} }}")[field]


def _mask_created(lists):
    return [{**x, "createdAt": "<timestamp>" if x["createdAt"] else None} for x in lists]


def _extract_legacy(data_dir):
    with tarfile.open(LEGACY_FIXTURE) as tar:
        tar.extractall(data_dir)


def test_legacy_trade_lists(client, data_dir):
    """A volume's trade_lists.json reads back exactly as the file-based app served
    it - lists, entry order, notes and priorities, and stale entries."""
    _extract_legacy(data_dir)
    shutil.copy(LEGACY_TRADE_LISTS, data_dir / "trade_lists.json")
    out = {"lists": trade_lists(client)}
    for lst in out["lists"]:
        out[lst["id"]] = list_players(client, lst["id"])
    check_golden("trade_lists_legacy", out)


def test_trade_list_crud(client, data_dir):
    _extract_legacy(data_dir)
    lid = LEGACY_LEAGUE
    L = f'leagueId: "{lid}"'
    out = {"empty": trade_lists(client)}

    created = [
        mutate(client, "createTradeList", f'{L}, name: "Top Targets"'),
        mutate(client, "createTradeList", f'{L}, name: "Top Targets"'),
        mutate(client, "createTradeList", f'{L}, name: "Bullpen!"'),
    ]
    out["created"] = _mask_created(created)
    out["create_blank"] = gql_error(
        client, f'mutation {{ createTradeList({L}, name: "  ") {{ id }} }}'
    )

    t = f'{L}, listId: "top-targets"'
    out["adds"] = [
        mutate(client, "addToTradeList", f'{t}, playerId: "1009"'),
        mutate(client, "addToTradeList", f'{t}, playerId: "1000", priority: "HIGH", note: "Glove first"'),
        mutate(client, "addToTradeList", f'{t}, playerId: "1002", priority: "LOW"'),
        mutate(client, "addToTradeList", f'{t}, playerId: "1104"'),
        mutate(client, "addToTradeList", f'{t}, playerId: "9999", note: "not in the league"'),
        # re-adding upserts in place and keeps the note when none is given
        mutate(client, "addToTradeList", f'{t}, playerId: "1000", priority: "LOW"'),
        mutate(client, "addToTradeList", f'{L}, listId: "top-targets-2", playerId: "1011"'),
    ]
    out["adds"] = _mask_created(out["adds"])
    out["add_errors"] = [
        gql_error(client, f'mutation {{ addToTradeList({t}, playerId: "1010", priority: "urgent") {{ id }} }}'),
        gql_error(client, f'mutation {{ addToTradeList({L}, listId: "nope", playerId: "1010") {{ id }} }}'),
        gql_error(client, f'mutation {{ addToTradeList({t}, playerId: " ") {{ id }} }}'),
    ]

    out["sets"] = _mask_created([
        mutate(client, "setTradeListEntry", f'{t}, playerId: "1009", note: "Bat speed"'),
        mutate(client, "setTradeListEntry", f'{t}, playerId: "1009", priority: "high"'),
        mutate(client, "setTradeListEntry", f'{t}, playerId: "1000", note: ""'),
    ])
    out["set_errors"] = [
        gql_error(client, f'mutation {{ setTradeListEntry({t}, playerId: "1010", note: "x") {{ id }} }}'),
        gql_error(client, f'mutation {{ setTradeListEntry({t}, playerId: "1009", priority: "meh") {{ id }} }}'),
    ]

    out["removed"] = _mask_created(
        [mutate(client, "removeFromTradeList", f'{t}, playerId: "1002"')]
    )
    out["remove_again"] = gql_error(
        client, f'mutation {{ removeFromTradeList({t}, playerId: "1002") {{ id }} }}'
    )

    out["renamed"] = _mask_created(
        [mutate(client, "renameTradeList", f'{L}, listId: "top-targets-2", name: "Bench Bats"')]
    )
    out["rename_errors"] = [
        gql_error(client, f'mutation {{ renameTradeList({L}, listId: "top-targets-2", name: "") {{ id }} }}'),
        gql_error(client, f'mutation {{ renameTradeList({L}, listId: "nope", name: "X") {{ id }} }}'),
    ]
    # the slug of a renamed list is free again only by id - a new "Bench Bats" gets its own
    out["create_after_rename"] = _mask_created(
        [mutate(client, "createTradeList", f'{L}, name: "Bench Bats"')]
    )

    out["deleted"] = mutate(client, "deleteTradeList", f'{L}, listId: "bullpen"', fields=None)
    out["delete_again"] = gql_error(
        client, f'mutation {{ deleteTradeList({L}, listId: "bullpen") }}'
    )

    out["final_lists"] = _mask_created(trade_lists(client))
    out["top_targets"] = list_players(client, "top-targets")
    out["bench_bats"] = list_players(client, "top-targets-2")
    out["unknown_list"] = gql_error(
        client, f'{{ tradeListPlayers({L}, listId: "nope") {{ totalRecords }} }}'
    )
    out["unknown_league"] = gql_error(
        client, '{ tradeLists(leagueId: "no-such-league") { id } }'
    )

    # deleting the league drops its lists; a league recreated under the same id
    # starts empty
    gql(client, f'mutation {{ deleteLeague(id: "{lid}") }}')
    assert create_league(client)["id"] == lid
    out["after_league_recreate"] = trade_lists(client)

    check_golden("trade_lists_crud", out)
