"""Per-run collection of debug "components" for each player.

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


def write_runtime_component(player_id, component_name: str, component_value: float):
    store = _current()
    if store.get(player_id) is None:
        store[player_id] = {}
    if component_value is not None and component_value > 0:
        # Coerce to a plain float: NumPy scalars survive `round()` and then
        # serialise as `np.float64(...)` under NumPy >= 2, which is not a
        # literal the reader can parse back. See web.service._parse_components.
        store[player_id][component_name] = round(float(component_value), 2)


def get_runtime_components(player_id):
    return _current().get(player_id, None)
