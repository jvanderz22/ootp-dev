"""Which ranking engine scores and serves a ranking: `legacy` (the rankers in
rankers/) or `v2` (the ranking/ package, see plans/ranking-v2-technical-plan.md).

Stored runs are kept per engine. The engine a web request reads is the one it
names in its `X-Ranking-Engine` header (the app's engine toggle), scoped to that
request; everything else - the CLI, background refreshes - uses the default.
"""
from contextlib import contextmanager
from contextvars import ContextVar

ENGINES = ("v2", "legacy")
DEFAULT_ENGINE = "v2"
HEADER = "x-ranking-engine"

_current = ContextVar("ranking_engine", default=DEFAULT_ENGINE)


def validate(engine: str) -> str:
    if engine not in ENGINES:
        raise ValueError(f"Unknown ranking engine {engine!r}; expected one of {ENGINES}.")
    return engine


def current() -> str:
    return _current.get()


@contextmanager
def using(engine: str):
    """Serve / score with `engine` inside the block."""
    token = _current.set(validate(engine))
    try:
        yield
    finally:
        _current.reset(token)


def get_ranker(method: str, engine: str = None):
    """A ranker for `method` under `engine` (default: the current one). Both
    kinds take `rank(players, batch_size=, progress=)` and return results
    best-first."""
    if validate(engine or current()) == "legacy":
        from rankers.get_ranker import get_ranker_for_method

        return get_ranker_for_method(method)
    from ranking import get_ranker as get_v2_ranker

    return get_v2_ranker(method)
