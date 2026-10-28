"""Per-run collection of each player's score breakdown.

Scorers and modifiers record intermediate values under a dotted path -
`batting.model.running`, `pitching.starter.pitch_mix`,
`batting.modifiers.AgeModifier` - and they accumulate into one nested dict per
player:

    {"batting":  {"model": {...}, "modifiers": {...}, "modifier_total": 1.04},
     "pitching": {"starter": {...}, "reliever": {...}, "modifiers": {...}, ...},
     "rank_adjust": {"modifiers": {...}, "pre_rank": 12, "pre_score": 61.3}}

Backed by a ContextVar so concurrent ranking runs (web requests) don't clobber
each other and memory doesn't leak across runs. `runtime_components_scope()`
wraps a single ranking pass; outside a scope the calls degrade to a shared dict
so the CLI and ad-hoc scripts keep working.
"""
import contextvars
from contextlib import contextmanager

_components: contextvars.ContextVar = contextvars.ContextVar("runtime_components")
_fallback: dict = {}


def _current() -> dict:
    try:
        return _components.get()
    except LookupError:
        return _fallback


@contextmanager
def runtime_components_scope():
    token = _components.set({})
    try:
        yield _components.get()
    finally:
        _components.reset(token)


def set_path(tree: dict, path: str, value) -> None:
    *parents, leaf = path.split(".")
    for key in parents:
        tree = tree.setdefault(key, {})
    tree[leaf] = value


def write_runtime_component(player_id, path: str, component_value) -> None:
    """Record `component_value` at `path` in the player's breakdown. Zero and
    negative values are kept - they are real results - only `None` is skipped."""
    if component_value is None:
        return
    # Coerce to a plain float: NumPy scalars would otherwise leak into the
    # stored JSON as non-native numbers.
    set_path(_current().setdefault(player_id, {}), path, round(float(component_value), 2))


def get_runtime_components(player_id):
    return _current().get(player_id, None)
