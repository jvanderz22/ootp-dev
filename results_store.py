"""Stored model runs - the `model_runs` / `run_results` tables.

A run is one ranking method scored over one source: a draft class's dataset
(scope "class", id = class name) or a league snapshot (scope "league", id =
league id). Only the latest run per (scope, id, method) is kept; `save_run`
replaces it in one transaction. A run is fresh while its `source_version`
matches the source's current version (`draft_classes.data_version` /
`league_snapshots.version`).

Each result row carries the scores plus the player's score breakdown, already
pruned to the side(s) his Hitter / Pitcher / Two-way type is judged on.
"""
import json
from datetime import datetime, timezone

import db

CLASS = "class"
LEAGUE = "league"

# run_results column -> the key the rest of the app (and the old ranked CSVs)
# call it
_RESULT_KEYS = {
    "player_id": "id",
    "name": "name",
    "position": "position",
    "age": "age",
    "player_type": "player_type",
    "model_score": "model_score",
    "raw_overall_score": "raw_overall_score",
    "position_player_score": "position_player_score",
    "batting_score": "batting_score_component",
    "fielding_score": "fielding_score_component",
    "running_score": "running_score_component",
    "best_position": "best_position",
    "pitcher_score": "pitcher_score",
    "starter_score": "starter_component",
    "reliever_score": "reliever_component",
    "in_game_overall": "in_game_overall",
    "in_game_potential": "in_game_potential",
    "demand": "demand",
}


def result_from_scored(s) -> dict:
    """A `ScoredPlayer` as a result row (keys as `load_results` returns them)."""
    return {
        "id": s.id,
        "name": s.name,
        "position": s.position,
        "age": s.age,
        "player_type": s.player_type,
        "model_score": round(s.overall_score, 2),
        "raw_overall_score": s.raw_overall_score,
        "position_player_score": s.position_player_score,
        "batting_score_component": s.batting_score_component,
        "fielding_score_component": s.fielding_score_component,
        "running_score_component": s.running_score_component,
        "best_position": s.best_position or "",
        "pitcher_score": s.pitcher_score,
        "starter_component": s.starter_component,
        "reliever_component": s.reliever_component,
        "in_game_overall": s.in_game_overall,
        "in_game_potential": s.in_game_potential,
        "demand": s.demand,
        "breakdown": s.breakdown,
    }


def save_run(scope, scope_id, method, source_version, results, scored_at=None) -> None:
    """Replace the stored run for (scope, scope_id, method) with `results` -
    result rows in model order, best first (see `result_from_scored`). A player
    id that repeats (a duplicated row in the export) keeps its best entry."""
    scored_at = scored_at or datetime.now(timezone.utc).isoformat()
    deduped, seen = [], set()
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    results = deduped
    columns = list(_RESULT_KEYS)
    insert = (
        "INSERT INTO run_results (scope, scope_id, method, model_rank, breakdown, "
        f"{', '.join(columns)}) VALUES ({', '.join('?' * (len(columns) + 5))})"
    )
    key = (scope, scope_id, method)
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM model_runs WHERE scope = ? AND scope_id = ? AND method = ?", key
        )
        conn.execute(
            "INSERT INTO model_runs (scope, scope_id, method, source_version, scored_at, "
            "player_count) VALUES (?, ?, ?, ?, ?, ?)",
            (*key, source_version, scored_at, len(results)),
        )
        conn.executemany(
            insert,
            [
                (*key, rank, json.dumps(r.get("breakdown") or {}, separators=(",", ":")),
                 *(r.get(_RESULT_KEYS[c]) for c in columns))
                for rank, r in enumerate(results, 1)
            ],
        )


def run_info(scope, scope_id, method):
    """`{source_version, scored_at, player_count}` of the stored run, or None."""
    row = db.query_one(
        "SELECT source_version, scored_at, player_count FROM model_runs "
        "WHERE scope = ? AND scope_id = ? AND method = ?",
        (scope, scope_id, method),
    )
    return dict(row) if row else None


def load_results(scope, scope_id, method, with_breakdown=False) -> list:
    """The run's result rows in model order. The breakdown is left out unless
    asked for - only the detail view and the CLI's verbose mode use it."""
    select = ", ".join(f"{c} AS {k}" for c, k in _RESULT_KEYS.items())
    if with_breakdown:
        select += ", breakdown"
    rows = db.query(
        f"SELECT {select} FROM run_results WHERE scope = ? AND scope_id = ? AND method = ? "
        "ORDER BY model_rank",
        (scope, scope_id, method),
    )
    out = [dict(r) for r in rows]
    if with_breakdown:
        for r in out:
            r["breakdown"] = json.loads(r["breakdown"])
    return out


def load_breakdown(scope, scope_id, method, player_id):
    """`(player_type, breakdown)` for one player of the run, or None."""
    row = db.query_one(
        "SELECT player_type, breakdown FROM run_results "
        "WHERE scope = ? AND scope_id = ? AND method = ? AND player_id = ?",
        (scope, scope_id, method, str(player_id)),
    )
    return (row["player_type"], json.loads(row["breakdown"])) if row else None


def class_results(ctx, with_breakdown=False):
    """A draft class's ranking for its current method, or None if it hasn't
    been scored since its dataset was last uploaded."""
    info = run_info(CLASS, ctx.name, ctx.ranking_method)
    if info is None or info["source_version"] != ctx.data_version:
        return None
    return load_results(CLASS, ctx.name, ctx.ranking_method, with_breakdown)


def delete_runs(scope, scope_id) -> None:
    db.execute("DELETE FROM model_runs WHERE scope = ? AND scope_id = ?", (scope, scope_id))


def flatten_breakdown(tree, prefix="") -> dict:
    """{"batting.modifiers.AgeModifier": 1.02, ...} - one entry per leaf."""
    out = {}
    for key, value in tree.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten_breakdown(value, f"{path}."))
        else:
            out[path] = value
    return out


def as_csv_rows(results) -> list:
    """Result rows in the string form the old ranked_players.csv had (None -> "",
    numbers via str()) plus its `overall_ranking` - for the CLI printers and the
    C+ export, so their output is unchanged. A loaded breakdown comes along,
    flattened, as `components`."""
    out = []
    for i, r in enumerate(results):
        row = {k: "" if v is None else str(v) for k, v in r.items() if k != "breakdown"}
        row["overall_ranking"] = str(i)
        if "breakdown" in r:
            row["components"] = flatten_breakdown(r["breakdown"])
        out.append(row)
    return out
