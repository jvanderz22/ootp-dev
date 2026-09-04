"""Process-level cache of fully-built ranked-player rows for a draft class.

Building a class's rows means reading the rankings CSV, resolving any custom
order, joining the raw scouting grid, and turning each player into the payload
the GraphQL layer serves. That work happens once here and is reused for every
subsequent filter / sort / page request until one of the class's source files
changes on disk or the entry ages out.
"""
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from custom_ranking import resolve_order
from drafted_players import get_drafted_players_info
from draft_class_files import (
    get_draft_class_drafted_players_file,
    get_ranked_players_file,
)
from rankers.get_ranker import RANKERS

_MAX_CLASSES = 8
_TTL_SECONDS = 1800  # 30 minutes

# Pitchers first, then scorekeeping order for position players.
POSITION_ORDER = [
    "P", "SP", "RP", "CL",
    "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "IF", "DH",
]

_cache: "OrderedDict[str, ClassIndex]" = OrderedDict()
_lock = threading.Lock()


@dataclass
class ClassIndex:
    name: str
    ranking_method: str
    built_at: float
    source_mtimes: tuple
    rows: list
    positions: list
    draft_teams: list

    def is_stale(self, ctx) -> bool:
        if time.monotonic() - self.built_at > _TTL_SECONDS:
            return True
        return self.source_mtimes != _source_mtimes(ctx)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _ranker_name(ctx) -> str:
    return RANKERS.get(ctx.ranking_method, RANKERS["draft_class"]).__name__


def _source_mtimes(ctx) -> tuple:
    return (
        _mtime(get_ranked_players_file(_ranker_name(ctx), ctx)),
        _mtime(ctx.data_file),
        _mtime(get_draft_class_drafted_players_file(ctx)),
        _mtime(ctx.custom_ranking_file),
    )


def _ordered_positions(positions) -> list:
    uniq = set(positions)
    known = [p for p in POSITION_ORDER if p in uniq]
    extra = sorted(p for p in uniq if p not in POSITION_ORDER)
    return known + extra


def _build_index(ctx) -> ClassIndex:
    from web import service  # lazy: service imports this module

    rows = service._read_ranked_rows(ctx)
    payloads = []
    if rows is not None:
        ordered = resolve_order(ctx, rows)
        drafted_info = get_drafted_players_info(ctx)
        game_players = service._game_players_by_id(ctx)
        payloads = [
            service._player_payload(i + 1, row, drafted_info, game_players.get(row["id"]))
            for i, row in enumerate(ordered)
        ]
    return ClassIndex(
        name=ctx.name,
        ranking_method=ctx.ranking_method,
        built_at=time.monotonic(),
        source_mtimes=_source_mtimes(ctx),
        rows=payloads,
        positions=_ordered_positions(p["position"] for p in payloads),
        draft_teams=sorted({p["drafted_team"] for p in payloads if p["drafted_team"]}),
    )


def get_index(ctx) -> ClassIndex:
    """Return the (possibly cached) built index for `ctx`, rebuilding if stale."""
    key = f"{ctx.name}:{ctx.ranking_method}"
    with _lock:
        cached = _cache.get(key)
        if cached is not None and not cached.is_stale(ctx):
            _cache.move_to_end(key)
            return cached
        idx = _build_index(ctx)
        _cache[key] = idx
        _cache.move_to_end(key)
        while len(_cache) > _MAX_CLASSES:
            _cache.popitem(last=False)
        return idx


def evict(name: str) -> None:
    """Drop every cached index for a class (any ranking method). Call after writes."""
    prefix = f"{name}:"
    with _lock:
        for key in [k for k in _cache if k.startswith(prefix)]:
            del _cache[key]
