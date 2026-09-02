"""Operations the GraphQL resolvers call. Keeps resolver functions thin and
keeps all filesystem / pipeline access in one place."""
import ast
import asyncio
import csv
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

import anyio

import pipeline
from context import DraftClassContext, default_base_dir
from custom_ranking import clear_order, has_custom_order, load_order, resolve_order, save_order
from draft_class_files import get_ranked_players_file
from drafted_players import get_drafted_player_ids
from load_draft_class import (
    DatasetFormatError,
    VALID_RANKING_METHODS,
    create_dataset_from_upload,
)
from rankers.get_ranker import RANKERS
from ranking_csv import build_upload_rows, write_upload_file
from statsplus_api import fetch_draft_picks, write_drafted_players_file
from web.settings import cookie_header, load_settings

_pipeline_lock = asyncio.Lock()

_FLOAT_FIELDS = (
    "model_score", "position_player_score", "fielding_score_component",
    "batting_score_component", "pitcher_score", "starter_component",
    "reliever_component", "raw_overall_score",
)


class NotFound(Exception):
    pass


class InvalidInput(Exception):
    pass


# --------------------------------------------------------------------- helpers
def _ctx(name: str) -> DraftClassContext:
    ctx = DraftClassContext(name)
    if not ctx.exists():
        raise NotFound(f"Draft class {name!r} not found.")
    return ctx


def _ranker_name(ctx) -> str:
    return RANKERS[ctx.ranking_method].__name__


def _dataset_ids(ctx) -> set:
    with open(ctx.data_file, newline="") as f:
        return {row["ID"] for row in csv.DictReader(f) if row.get("ID")}


def _dataset_count(ctx) -> int:
    with open(ctx.data_file, newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _parse_components(raw):
    if not raw:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(raw)
        except (ValueError, SyntaxError):
            continue
    return None


def _read_ranked_rows(ctx):
    path = get_ranked_players_file(_ranker_name(ctx), ctx)
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _player_payload(rank, row, drafted_ids):
    payload = {
        "rank": rank,
        "id": row["id"],
        "name": row["name"],
        "position": row["position"],
        "age": _to_int(row.get("age")),
        "in_game_potential": _to_int(row.get("in_game_potential")),
        "demand": row.get("demand") or None,
        "drafted": row["id"] in drafted_ids,
        "components": _parse_components(row.get("components")),
    }
    for field in _FLOAT_FIELDS:
        payload[field] = _to_number(row.get(field))
    return payload


# ----------------------------------------------------------------- read models
def draft_class_payload(name: str):
    ctx = DraftClassContext(name)
    if not ctx.exists():
        return None
    try:
        ranking_method = ctx.ranking_method
    except (FileNotFoundError, json.JSONDecodeError):
        ranking_method = "draft_class"

    ranked_path = get_ranked_players_file(RANKERS.get(ranking_method, RANKERS["draft_class"]).__name__, ctx)
    last_processed = None
    if os.path.exists(ranked_path):
        last_processed = datetime.fromtimestamp(
            os.path.getmtime(ranked_path), tz=timezone.utc
        ).isoformat()

    drafted_ids = get_drafted_player_ids(ctx)
    drafted_count = len(drafted_ids & _dataset_ids(ctx)) if drafted_ids else 0

    return {
        "name": name,
        "ranking_method": ranking_method,
        "player_count": _dataset_count(ctx),
        "has_custom_order": has_custom_order(ctx),
        "last_processed": last_processed,
        "drafted_count": drafted_count,
    }


def list_draft_classes():
    return [
        payload
        for name in DraftClassContext.list_classes()
        if (payload := draft_class_payload(name)) is not None
    ]


def ranked_players(name: str):
    ctx = _ctx(name)
    rows = _read_ranked_rows(ctx)
    if rows is None:
        return []  # not processed yet - the UI still needs to render (Reprocess/Delete)
    ordered = resolve_order(ctx, rows)
    drafted_ids = get_drafted_player_ids(ctx)
    return [_player_payload(i + 1, row, drafted_ids) for i, row in enumerate(ordered)]


def upload_csv_bytes(name: str) -> bytes:
    ctx = _ctx(name)
    if _read_ranked_rows(ctx) is None:
        raise InvalidInput(f"Draft class {name!r} has not been processed yet.")
    buf = []
    for row in build_upload_rows(ctx):
        buf.append(
            ",".join(
                str(row[k]) for k in ("id", "name", "position", "age", "model_score", "demand")
            )
        )
    return ("\r\n".join(buf) + "\r\n").encode()


# --------------------------------------------------------------------- mutations
async def _run_pipeline(ctx):
    async with _pipeline_lock:
        try:
            await anyio.to_thread.run_sync(pipeline.process_class, ctx)
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidInput(
                f"Couldn't rank this class: {exc}. The export is probably missing "
                f"rating columns the model needs."
            ) from exc


def delete_draft_class(name: str) -> str:
    ctx = _ctx(name)
    for path in (ctx.data_file, ctx.processed_dir):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    return name


async def upload_draft_class(name: str, ranking_method: str, upload):
    name = (name or "").strip()
    if not name or "/" in name or name.startswith("."):
        raise InvalidInput("Invalid class name.")
    if ranking_method not in VALID_RANKING_METHODS:
        raise InvalidInput(f"Unknown ranking method {ranking_method!r}.")

    fd, tmp_path = tempfile.mkstemp(prefix="upload-", dir=str(default_base_dir()))
    try:
        with os.fdopen(fd, "wb") as tmp:
            while chunk := await anyio.to_thread.run_sync(upload.file.read, 1 << 20):
                tmp.write(chunk)
        try:
            ctx = await anyio.to_thread.run_sync(
                create_dataset_from_upload, name, tmp_path, ranking_method
            )
        except DatasetFormatError as exc:
            raise InvalidInput(str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    await _run_pipeline(ctx)
    return draft_class_payload(name)


async def set_ranking_method(name: str, ranking_method: str):
    ctx = _ctx(name)
    if ranking_method not in VALID_RANKING_METHODS:
        raise InvalidInput(f"Unknown ranking method {ranking_method!r}.")
    config = ctx.load_config()
    config["ranking_method"] = ranking_method
    ctx.save_config(config)
    await _run_pipeline(ctx)
    return draft_class_payload(name)


async def reprocess(name: str):
    ctx = _ctx(name)
    await _run_pipeline(ctx)
    return draft_class_payload(name)


def save_custom_order(name: str, order):
    ctx = _ctx(name)
    rows = _read_ranked_rows(ctx)
    if rows is None:
        raise InvalidInput(f"Draft class {name!r} has not been processed yet.")
    known = [r["id"] for r in rows]
    save_order(ctx, [str(pid) for pid in order], known_ids=known)
    write_upload_file(ctx)
    return ranked_players(name)


def clear_custom_order(name: str):
    ctx = _ctx(name)
    clear_order(ctx)
    if _read_ranked_rows(ctx) is not None:
        write_upload_file(ctx)
    return ranked_players(name)


async def refresh_drafted(name: str):
    return await anyio.to_thread.run_sync(_refresh_drafted_sync, name)


def _refresh_drafted_sync(name: str):
    ctx = _ctx(name)
    settings = load_settings()
    picks = fetch_draft_picks(
        settings.get("league_url"),
        cookie_header(settings),
        settings.get("default_lid"),
    )
    write_drafted_players_file(ctx, picks)
    if _read_ranked_rows(ctx) is not None:
        write_upload_file(ctx)

    dataset_ids = _dataset_ids(ctx)
    matched = sum(1 for p in picks if p.id in dataset_ids)
    return {
        "drafted_count": matched,
        "matched_by_id": matched,
        "matched_by_name": 0,
        "unmatched": len(picks) - matched,
    }
