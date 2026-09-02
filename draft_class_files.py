"""Backwards-compatible path helpers.

These now delegate to a DraftClassContext. Passing `ctx` explicitly is the
supported path for the web app; omitting it falls back to a context built from
constants.DRAFT_CLASS_NAME so the CLI entry points keep working untouched.
"""
from context import DraftClassContext


def _ctx(ctx=None) -> DraftClassContext:
    if ctx is not None:
        return ctx
    from constants import DRAFT_CLASS_NAME

    return DraftClassContext(DRAFT_CLASS_NAME)


def get_draft_class_data_file(ctx=None) -> str:
    return str(_ctx(ctx).data_file)


def get_ranker_folder(ranker, ctx=None) -> str:
    return str(_ctx(ctx).ranker_dir(ranker))


def get_draft_class_eval_model_file(ranker, ctx=None) -> str:
    return str(_ctx(ctx).eval_model_file(ranker))


def get_draft_class_config_file(ctx=None) -> str:
    return str(_ctx(ctx).config_file)


def get_ranked_players_file(ranker, ctx=None) -> str:
    return str(_ctx(ctx).ranked_players_file(ranker))


def get_draft_class_upload_players_file(ctx=None) -> str:
    return str(_ctx(ctx).upload_players_file)


def get_draft_class_drafted_players_file(ctx=None) -> str:
    return str(_ctx(ctx).drafted_players_file)
