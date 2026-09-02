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
def resolve_ranked_players(_, __, name):
    return service.ranked_players(name)


@query.field("statsPlusSettings")
def resolve_settings(*_):
    return public_settings()
