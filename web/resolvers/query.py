from functools import partial

import anyio
from ariadne import QueryType

from web import service
from web.settings import public_settings

query = QueryType()


async def _off_loop(fn, *args, **kwargs):
    """Run a blocking service call on a worker thread so the event loop stays
    free. The ranking/snapshot calls parse 15k-row CSVs (and sometimes re-score
    the whole pool); left on the loop they freeze every other request, /healthz
    included."""
    return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))


@query.field("draftClasses")
async def resolve_draft_classes(*_):
    return await _off_loop(service.list_draft_classes)


@query.field("draftClass")
async def resolve_draft_class(_, __, name):
    return await _off_loop(service.draft_class_payload, name)


@query.field("rankedPlayers")
async def resolve_ranked_players(
    _, __, name, filter=None, sort=None, page=0, page_size=50, all_rows=False
):
    return await _off_loop(
        service.ranked_players_page,
        name,
        filter=filter,
        sort=sort,
        page=page,
        page_size=page_size,
        all_rows=all_rows,
    )


@query.field("classPositions")
async def resolve_class_positions(_, __, name):
    return await _off_loop(service.class_positions, name)


@query.field("draftTeams")
async def resolve_draft_teams(_, __, name):
    return await _off_loop(service.draft_teams, name)


@query.field("statsPlusSettings")
def resolve_settings(*_):
    return public_settings()


@query.field("leagues")
async def resolve_leagues(*_):
    return await _off_loop(service.list_leagues)


@query.field("leagueSnapshot")
async def resolve_league_snapshot(_, __, league_id):
    return await _off_loop(service.league_snapshot_payload, league_id)


@query.field("leagueSnapshotPlayers")
async def resolve_league_snapshot_players(
    _,
    __,
    league_id,
    method,
    group_by,
    group_id=None,
    filter=None,
    sort=None,
    page=0,
    page_size=50,
    all_rows=False,
):
    return await _off_loop(
        service.league_snapshot_players_page,
        league_id,
        method,
        group_by=group_by,
        group_id=group_id,
        filter=filter,
        sort=sort,
        page=page,
        page_size=page_size,
        all_rows=all_rows,
    )


@query.field("leagueOrgs")
async def resolve_league_orgs(_, __, league_id):
    return await _off_loop(service.list_league_orgs, league_id)


@query.field("leagueTeams")
async def resolve_league_teams(_, __, league_id):
    return await _off_loop(service.list_league_teams, league_id)


@query.field("leagueRefreshStatus")
async def resolve_league_refresh_status(_, __, league_id):
    return await _off_loop(service.league_refresh_status, league_id)
