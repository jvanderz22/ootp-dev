from ariadne import MutationType

from web import service

mutation = MutationType()


@mutation.field("uploadDraftClass")
async def resolve_upload(_, __, name, ranking_method, file):
    return await service.upload_draft_class(name, ranking_method, file)


@mutation.field("setRankingMethod")
async def resolve_set_ranking_method(_, __, name, ranking_method):
    return await service.set_ranking_method(name, ranking_method)


@mutation.field("reprocessDraftClass")
async def resolve_reprocess(_, __, name):
    return await service.reprocess(name)


@mutation.field("deleteDraftClass")
def resolve_delete(_, __, name):
    return service.delete_draft_class(name)


@mutation.field("saveCustomOrder")
def resolve_save_custom_order(_, __, name, order):
    return service.save_custom_order(name, order)


@mutation.field("setPlayerRank")
def resolve_set_player_rank(_, __, name, id, rank):
    return service.set_player_rank(name, id, rank)


@mutation.field("clearCustomOrder")
def resolve_clear_custom_order(_, __, name):
    return service.clear_custom_order(name)


@mutation.field("refreshDraftedFromStatsPlus")
async def resolve_refresh_drafted(_, __, name):
    return await service.refresh_drafted(name)


@mutation.field("createLeague")
def resolve_create_league(
    _,
    __,
    name,
    league_url=None,
    default_lid=None,
    class_names=None,
    sessionid=None,
    csrftoken=None,
    game_league_ids=None,
):
    return service.create_league(
        name, league_url, default_lid, class_names, sessionid, csrftoken,
        game_league_ids=game_league_ids,
    )


@mutation.field("updateLeague")
def resolve_update_league(
    _,
    __,
    id,
    name=None,
    league_url=None,
    default_lid=None,
    class_names=None,
    sessionid=None,
    csrftoken=None,
    game_league_ids=None,
):
    return service.update_league(
        id, name, league_url, default_lid, class_names, sessionid, csrftoken,
        game_league_ids=game_league_ids,
    )


@mutation.field("deleteLeague")
def resolve_delete_league(_, __, id):
    return service.delete_league(id)


@mutation.field("setClassLeague")
def resolve_set_class_league(_, __, name, league_id=None):
    return service.set_class_league(name, league_id)


@mutation.field("refreshLeagueSnapshot")
async def resolve_refresh_league_snapshot(_, __, league_id):
    """Starts a background refresh and returns its status right away; the client
    polls `leagueRefreshStatus` for progress."""
    return await service.refresh_league_snapshot(league_id)


@mutation.field("checkLeagueSnapshotFreshness")
async def resolve_check_league_snapshot_freshness(_, __, league_id):
    return await service.check_league_snapshot_freshness(league_id)
