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


@query.field("statsPlusSettings")
def resolve_settings(*_):
    return public_settings()
