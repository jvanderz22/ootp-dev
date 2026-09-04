from ariadne import MutationType

from web import service
from web.settings import public_settings, update_settings

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


@mutation.field("updateStatsPlusSettings")
def resolve_update_settings(_, __, sessionid=None, csrftoken=None):
    update_settings(sessionid=sessionid, csrftoken=csrftoken)
    return public_settings()


@mutation.field("createLeague")
def resolve_create_league(_, __, name, league_url=None, default_lid=None, class_names=None):
    return service.create_league(name, league_url, default_lid, class_names)


@mutation.field("updateLeague")
def resolve_update_league(
    _, __, id, name=None, league_url=None, default_lid=None, class_names=None
):
    return service.update_league(id, name, league_url, default_lid, class_names)


@mutation.field("deleteLeague")
def resolve_delete_league(_, __, id):
    return service.delete_league(id)


@mutation.field("setClassLeague")
def resolve_set_class_league(_, __, name, league_id=None):
    return service.set_class_league(name, league_id)
