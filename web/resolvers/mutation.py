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
def resolve_update_settings(
    _, __, league_url=None, sessionid=None, csrftoken=None, default_lid=None
):
    update_settings(
        league_url=league_url,
        sessionid=sessionid,
        csrftoken=csrftoken,
        default_lid=default_lid,
    )
    return public_settings()
