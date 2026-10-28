"""Backwards-compatible class lookup for the CLI entry points.

Passing `ctx` explicitly is the supported path for the web app; omitting it
falls back to a context built from constants.DRAFT_CLASS_NAME so the CLI
scripts keep working untouched.
"""
from context import DraftClassContext


def _ctx(ctx=None) -> DraftClassContext:
    if ctx is not None:
        return ctx
    from constants import DRAFT_CLASS_NAME

    return DraftClassContext(DRAFT_CLASS_NAME)


def get_draft_class_data_file(ctx=None) -> str:
    return str(_ctx(ctx).data_file)


def get_draft_class_upload_players_file(ctx=None) -> str:
    return str(_ctx(ctx).upload_players_file)
