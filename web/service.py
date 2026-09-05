"""Operations the GraphQL resolvers call. Keeps resolver functions thin and
keeps all filesystem / pipeline access in one place."""
import ast
import asyncio
import csv
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

import anyio

import pipeline
from context import DraftClassContext, default_base_dir
from web import class_index, leagues
from custom_ranking import clear_order, has_custom_order, load_order, resolve_order, save_order
from draft_class_files import get_ranked_players_file
from drafted_players import get_drafted_player_ids
from models.game_players import GamePlayers
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
    "reliever_component", "running_score_component", "raw_overall_score",
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


# NumPy >= 2 renders scalars as `np.float64(1.02)` in a dict's repr, which is a
# call expression, not a literal — `ast.literal_eval` chokes on it. Older CSVs
# written under such a build have those wrappers baked into the `components`
# column; strip them so the data stays readable without a re-process.
_NP_SCALAR_RE = re.compile(r"np\.\w+\(([^()]*)\)")


def _parse_components(raw):
    if not raw:
        return None
    for candidate in (raw, _NP_SCALAR_RE.sub(r"\1", raw)):
        for parser in (json.loads, ast.literal_eval):
            try:
                return parser(candidate)
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


def _game_players_by_id(ctx):
    """The raw scouting grid for this class, keyed by OOTP id, for the detail view."""
    try:
        with open(ctx.data_file, newline="") as f:
            return GamePlayers(list(csv.DictReader(f))).game_players_by_id
    except FileNotFoundError:
        return {}


def _pitch_ratings(gp):
    out = []
    for field in gp.pitch_fields:
        potential = getattr(gp, field)
        if potential is None:
            continue
        out.append(
            {
                "name": field.capitalize(),
                "potential": potential,
                "current": getattr(gp, f"{field}_ovr"),
            }
        )
    out.sort(key=lambda p: p["potential"], reverse=True)
    return out


def _ratings_payload(gp):
    """The scouting attributes the CLI printers show, grouped by hitter / pitcher."""
    if gp is None:
        return None
    return {
        "batHand": gp.bat_hand or None,
        "throwHand": gp.throw_hand or None,
        "injuryProne": gp.injury_prone or None,
        "workEthic": gp.work_ethic or None,
        "intelligence": gp.intelligence or None,
        "leadership": gp.leadership or None,
        "scoutingAccuracy": gp.scouting_accuracy or None,
        "batting": {
            "contact": gp.contact,
            "gap": gp.gap,
            "power": gp.power,
            "eye": gp.eye,
            "avoidK": gp.avoid_k,
            "contactCur": gp.contact_ovr,
            "gapCur": gp.gap_ovr,
            "powerCur": gp.power_ovr,
            "eyeCur": gp.eye_ovr,
            "avoidKCur": gp.avoid_k_ovr,
            "speed": gp.speed,
            "steal": gp.steal,
            "running": gp.running_ability,
        },
        "fielding": {
            "ifRange": gp.if_range,
            "ifArm": gp.if_arm,
            "ifError": gp.if_error,
            "turnDp": gp.turn_dp,
            "ofRange": gp.of_range,
            "ofArm": gp.of_arm,
            "ofError": gp.of_error,
            "cFraming": gp.c_framing,
            "cBlocking": gp.c_blocking,
            "cArm": gp.c_arm,
        },
        "pitching": {
            "stuff": gp.stuff,
            "movement": gp.movement,
            "control": gp.control,
            "stuffCur": gp.stuff_ovr,
            "movementCur": gp.movement_ovr,
            "controlCur": gp.control_ovr,
            "stamina": gp.stamina,
            "velocity": gp.velocity or None,
            "groundballType": gp.groundball_type or None,
            "armSlot": gp.arm_slot or None,
            "pitches": _pitch_ratings(gp),
        },
    }


def _classify(position_player_score, pitcher_score):
    """Hitter / Pitcher / Two-way, mirroring printers/draft_prospect_printer.py."""
    pp = position_player_score or 0
    pit = pitcher_score or 0
    hi, lo = max(pp, pit), min(pp, pit)
    if hi > 0 and lo * 2 > hi:
        return "Two-way"
    return "Pitcher" if pit >= pp else "Hitter"


def _player_payload(rank, row, drafted_info, game_player=None):
    info = (drafted_info or {}).get(row["id"])
    payload = {
        "rank": rank,
        "id": row["id"],
        "name": row["name"],
        "position": row["position"],
        "age": _to_int(row.get("age")),
        "bat_hand": (getattr(game_player, "bat_hand", None) or None) if game_player else None,
        "throw_hand": (getattr(game_player, "throw_hand", None) or None) if game_player else None,
        "in_game_overall": _to_int(row.get("in_game_overall")),
        "in_game_potential": _to_int(row.get("in_game_potential")),
        "demand": row.get("demand") or None,
        "drafted": info is not None,
        "drafted_team": (info.get("team") or None) if info else None,
        "drafted_pick": _to_int(info.get("overall_selection")) if info else None,
        "drafted_round": _to_int(info.get("round")) if info else None,
        "drafted_round_pick": _to_int(info.get("round_selection")) if info else None,
        "components": _parse_components(row.get("components")),
        "ratings": _ratings_payload(game_player),
    }
    for field in _FLOAT_FIELDS:
        payload[field] = _to_number(row.get(field))
    payload["type"] = _classify(
        payload["position_player_score"], payload["pitcher_score"]
    )
    return payload


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


def _demand_key(demand):
    """Numeric sort key for the contract-demand column. Mirrors demandSortKey in
    frontend/src/app/core/player-stats.ts ("Slot" = 0, "Impossible" sorts last)."""
    if not demand:
        return None
    s = demand.strip().lower()
    if s == "slot":
        return 0.0
    if s == "impossible":
        return 9.99e11
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return None
    n = float(digits)
    if s.endswith("k"):
        return n * 1_000
    if s.endswith("m"):
        return n * 100_000
    return n


# Descriptive scouting grades (personality, injury proneness, scout accuracy)
# ordered low -> high so the table can sort them meaningfully. Only relative
# order within a single column matters, so overlapping vocabularies are fine.
_GRADE_ORDINALS = {
    "l": 0, "n": 1, "h": 2,
    "fragile": 0, "normal": 1, "durable": 2,
    "very low": 0, "low": 1, "average": 2, "high": 3, "very high": 4,
}
_RATING_META_KEYS = {
    "injuryProne", "workEthic", "intelligence", "leadership", "scoutingAccuracy",
}


def _grade_ordinal(value):
    if value is None:
        return None
    return _GRADE_ORDINALS.get(str(value).strip().lower())


def _sort_value(row, field):
    """Resolve a column's sort value: a flat payload key (camelCase from the
    client), a top-level `ratings` grade, a dotted rating path (`batting.power`,
    `pitching.stuff`), or `pitch.<Name>` for an individual pitch potential."""
    if field == "demandKey":
        return _demand_key(row.get("demand"))
    if field in _RATING_META_KEYS:
        return _grade_ordinal((row.get("ratings") or {}).get(field))
    if "." not in field:
        return row.get(_camel_to_snake(field))
    head, _, tail = field.partition(".")
    ratings = row.get("ratings") or {}
    if head == "pitch":
        for p in (ratings.get("pitching") or {}).get("pitches") or []:
            if p.get("name", "").lower() == tail.lower():
                return p.get("potential")
        return None
    return (ratings.get(head) or {}).get(tail)


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

    league = leagues.league_for_class(name)

    return {
        "name": name,
        "ranking_method": ranking_method,
        "player_count": _dataset_count(ctx),
        "has_custom_order": has_custom_order(ctx),
        "last_processed": last_processed,
        "drafted_count": drafted_count,
        "league_id": league["id"] if league else None,
        "league_name": league["name"] if league else None,
    }


# --------------------------------------------------------------------- leagues
def _league_payload(league: dict) -> dict:
    return {**league, "class_names": leagues.class_names_for_league(league["id"])}


def list_leagues():
    all_leagues = leagues.load_leagues()
    buckets = {lg["id"]: [] for lg in all_leagues}
    for cname in DraftClassContext.list_classes():
        lg = leagues.league_for_class(cname)
        if lg and lg["id"] in buckets:
            buckets[lg["id"]].append(cname)
    return [{**lg, "class_names": sorted(buckets[lg["id"]])} for lg in all_leagues]


def create_league(name, league_url=None, default_lid=None, class_names=None):
    try:
        league = leagues.create_league(name, league_url, default_lid, class_names)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    return _league_payload(league)


def update_league(id, name=None, league_url=None, default_lid=None, class_names=None):
    try:
        league = leagues.update_league(id, name, league_url, default_lid, class_names)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    return _league_payload(league)


def delete_league(id):
    try:
        return leagues.delete_league(id)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


def set_class_league(name, league_id):
    _ctx(name)
    try:
        leagues.set_class_league(name, league_id)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    return draft_class_payload(name)


def list_draft_classes():
    return [
        payload
        for name in DraftClassContext.list_classes()
        if (payload := draft_class_payload(name)) is not None
    ]


def _apply_numeric_filter(rows, nf):
    """Keep rows whose `nf['field']` value sits within the inclusive
    [min, max] bounds. Reuses `_sort_value` so any sortable column (flat key,
    dotted rating path, `pitch.<Name>`, `demandKey`, grade meta key) is
    filterable; graded columns compare on their tier ordinal. Rows with a
    missing or non-numeric value for the field are dropped."""
    field = (nf or {}).get("field")
    lo = (nf or {}).get("min")
    hi = (nf or {}).get("max")
    if not field or (lo is None and hi is None):
        return rows

    def keep(row):
        value = _sort_value(row, field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if lo is not None and value < lo:
            return False
        if hi is not None and value > hi:
            return False
        return True

    return [r for r in rows if keep(r)]


def ranked_players_page(
    name: str, *, filter=None, sort=None, page=0, page_size=50, all_rows=False
):
    """One filtered/sorted/paginated slice of a class, served from the in-memory
    index (see web/class_index.py). `filter` = {search, positions, hide_drafted};
    `sort` = {field, order} with order 1 asc / -1 desc."""
    idx = class_index.get_index(_ctx(name))
    rows = idx.rows

    f = filter or {}
    search = (f.get("search") or "").strip().lower()
    pos_set = set(f.get("positions") or [])
    bat_set = set(f.get("bat_hands") or [])
    throw_set = set(f.get("throw_hands") or [])
    team_set = set(f.get("teams") or [])
    hide_drafted = bool(f.get("hide_drafted"))
    if search or pos_set or bat_set or throw_set or team_set or hide_drafted:
        rows = [
            r
            for r in rows
            if (not search or search in r["name"].lower())
            and (not pos_set or r["position"] in pos_set)
            and (not bat_set or r["bat_hand"] in bat_set)
            and (not throw_set or r["throw_hand"] in throw_set)
            and (not team_set or r["drafted_team"] in team_set)
            and (not hide_drafted or not r["drafted"])
        ]

    for nf in f.get("numeric") or []:
        rows = _apply_numeric_filter(rows, nf)

    total = len(rows)

    if sort and sort.get("field"):
        reverse = (sort.get("order") or 1) < 0
        keyed = [(r, _sort_value(r, sort["field"])) for r in rows]
        present = [(r, v) for r, v in keyed if v is not None]
        missing = [r for r, v in keyed if v is None]
        present.sort(key=lambda t: t[1], reverse=reverse)  # stable: ties keep rank order
        rows = [r for r, _ in present] + missing

    if not all_rows:
        start = max(page, 0) * page_size
        rows = rows[start : start + page_size]

    return {"rows": rows, "total_records": total}


def ranked_players(name: str):
    """Full ordered list, no filter/sort/paging - custom-order internals and tests."""
    return ranked_players_page(name, all_rows=True)["rows"]


def class_positions(name: str):
    return class_index.get_index(_ctx(name)).positions


def draft_teams(name: str):
    """Distinct teams that have made a pick in this class, for the team filter."""
    return class_index.get_index(_ctx(name)).draft_teams


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
    class_index.evict(name)
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
    class_index.evict(name)
    return draft_class_payload(name)


async def set_ranking_method(name: str, ranking_method: str):
    ctx = _ctx(name)
    if ranking_method not in VALID_RANKING_METHODS:
        raise InvalidInput(f"Unknown ranking method {ranking_method!r}.")
    config = ctx.load_config()
    config["ranking_method"] = ranking_method
    ctx.save_config(config)
    await _run_pipeline(ctx)
    class_index.evict(name)
    return draft_class_payload(name)


async def reprocess(name: str):
    ctx = _ctx(name)
    await _run_pipeline(ctx)
    class_index.evict(name)
    return draft_class_payload(name)


def save_custom_order(name: str, order):
    ctx = _ctx(name)
    rows = _read_ranked_rows(ctx)
    if rows is None:
        raise InvalidInput(f"Draft class {name!r} has not been processed yet.")
    known = [r["id"] for r in rows]
    save_order(ctx, [str(pid) for pid in order], known_ids=known)
    write_upload_file(ctx)
    class_index.evict(name)
    return draft_class_payload(name)


def set_player_rank(name: str, player_id, rank):
    """Move one player to 1-based `rank` in the current order, shifting everyone
    else, and persist the result as the class's custom order."""
    ctx = _ctx(name)
    if _read_ranked_rows(ctx) is None:
        raise InvalidInput(f"Draft class {name!r} has not been processed yet.")
    order = [str(r["id"]) for r in class_index.get_index(ctx).rows]
    pid = str(player_id)
    if pid not in order:
        raise InvalidInput(f"Player {player_id!r} is not in draft class {name!r}.")
    try:
        target = int(rank)
    except (TypeError, ValueError):
        raise InvalidInput("Rank must be a whole number.")
    order.remove(pid)
    target = max(1, min(target, len(order) + 1)) - 1
    order.insert(target, pid)
    save_order(ctx, order, known_ids=order)
    write_upload_file(ctx)
    class_index.evict(name)
    return draft_class_payload(name)


def clear_custom_order(name: str):
    ctx = _ctx(name)
    clear_order(ctx)
    if _read_ranked_rows(ctx) is not None:
        write_upload_file(ctx)
    class_index.evict(name)
    return draft_class_payload(name)


async def refresh_drafted(name: str):
    return await anyio.to_thread.run_sync(_refresh_drafted_sync, name)


def _refresh_drafted_sync(name: str):
    ctx = _ctx(name)
    league = leagues.league_for_class(name)
    if not league:
        raise InvalidInput(
            f"Draft class {name!r} isn't assigned to a league yet. Assign one from "
            f"the class menu (Move to league…) or the Settings page, then retry."
        )
    if not league.get("league_url"):
        raise InvalidInput(
            f"League {league['name']!r} has no StatsPlus URL. Add one on the Settings page."
        )
    settings = load_settings()
    picks = fetch_draft_picks(
        league["league_url"],
        cookie_header(settings),
        league.get("default_lid"),
    )
    write_drafted_players_file(ctx, picks)
    if _read_ranked_rows(ctx) is not None:
        write_upload_file(ctx)
    class_index.evict(name)

    dataset_ids = _dataset_ids(ctx)
    matched = sum(1 for p in picks if p.id in dataset_ids)
    return {
        "drafted_count": matched,
        "matched_by_id": matched,
        "matched_by_name": 0,
        "unmatched": len(picks) - matched,
    }
