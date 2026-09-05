from ariadne import QueryType

from web import service
from web.settings import public_settings

query = QueryType()


@query.field("draftClasses")
def resolve_draft_classes(*_):
    return service.list_draft_classes()


@query.field("draftClass")
def resolve_draft_class(_, __, name):
    return service.draft_class_payload(name)


@query.field("rankedPlayers")
def resolve_ranked_players(
    _, __, name, filter=None, sort=None, page=0, page_size=50, all_rows=False
):
    return service.ranked_players_page(
        name,
        filter=filter,
        sort=sort,
        page=page,
        page_size=page_size,
        all_rows=all_rows,
    )


@query.field("classPositions")
def resolve_class_positions(_, __, name):
    return service.class_positions(name)


@query.field("draftTeams")
def resolve_draft_teams(_, __, name):
    return service.draft_teams(name)


@query.field("statsPlusSettings")
def resolve_settings(*_):
    return public_settings()


@query.field("leagues")
def resolve_leagues(*_):
    return service.list_leagues()


@query.field("leagueSnapshot")
def resolve_league_snapshot(_, __, league_id):
    return service.league_snapshot_payload(league_id)


@query.field("leagueSnapshotPlayers")
def resolve_league_snapshot_players(
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
    return service.league_snapshot_players_page(
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
def resolve_league_orgs(_, __, league_id):
    return service.list_league_orgs(league_id)


@query.field("leagueTeams")
def resolve_league_teams(_, __, league_id):
    return service.list_league_teams(league_id)
