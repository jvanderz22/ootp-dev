"""One-time import of a pre-SQLite $DATA_DIR into the database.

Before the database every piece of state was a file under $DATA_DIR:

    leagues.json                                   (older: web_config.json / STATSPLUS_* env)
    processed_classes/<class>/config.json          ranking method, print method, league pin
    processed_classes/<class>/custom_ranking.json  {"order": [ids]}
    processed_classes/<class>/drafted_players.csv  StatsPlus API (`id` column) or name-scrape rows
    processed_classes/<class>/<Ranker>/ranked_players.csv     the scored ranking
    league_snapshots/<league>/meta.json            fetch / check times, counts, in-game date
    league_snapshots/<league>/<Ranker>/ranked_players.csv     the scored rankings
    trade_lists.json                               per-league trade-target lists

`db._migration_1` calls `import_legacy_files` and `db._migration_2` calls
`import_trade_lists`, each exactly once inside its migration transaction, so a
partial import never commits. The files are left where they
are; the datasets and snapshot CSVs are still read from disk.

The ranked CSVs come in as stored runs (`results_store`), their stringified
`components` dicts mapped onto the nested score breakdown, so an upgraded
install serves the same rankings without re-scoring anything.
"""
import ast
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import db
import results_store
from models.player_type import classify, prune_breakdown
from scoring.runtime_components import set_path


def import_legacy_files(base_dir) -> None:
    base_dir = Path(base_dir)
    _import_leagues(base_dir)
    _import_classes(base_dir)
    _import_snapshots(base_dir)
    db.execute(
        "INSERT INTO app_meta (key, value) VALUES ('files_imported_at', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )


def _read_json(path: Path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- leagues
def _import_leagues(base_dir: Path) -> None:
    from web import leagues as lg

    data = _read_json(base_dir / "leagues.json")
    if isinstance(data, dict):
        found = [lg._clean(x) for x in data.get("leagues", []) if x.get("id")]
        if not data.get("cookies_seeded"):
            found = _seed_legacy_cookies(found)
    else:
        found = _league_from_legacy_config()
    for league in found:
        lg._save(league)


def _seed_legacy_cookies(found: list) -> list:
    """leagues.json from before per-league cookies: give every league without a
    cookie the old app-wide one (web_config.json / STATSPLUS_* env)."""
    from web.settings import legacy_cookie

    cookie = legacy_cookie()
    if cookie:
        for league in found:
            if not league.get("sessionid") and not league.get("csrftoken"):
                league["sessionid"] = cookie.get("sessionid", "")
                league["csrftoken"] = cookie.get("csrftoken", "")
    return found


def _league_from_legacy_config() -> list:
    """An install from before leagues existed: fold the single app-wide
    `league_url` / `default_lid` / cookie into one league."""
    from web import leagues as lg
    from web.settings import legacy_cookie, legacy_league_config

    legacy = legacy_league_config()
    url = legacy.get("league_url") or ""
    if not url:
        return []
    name = ""
    m = re.search(r"/([^/]+)/?$", url.rstrip("/"))
    if m:
        name = m.group(1)
    cookie = legacy_cookie()
    return [
        lg._clean(
            {
                "id": lg._slugify(name) if name else "default",
                "name": name or "Default",
                "league_url": url,
                "default_lid": legacy.get("default_lid"),
                "sessionid": cookie.get("sessionid", ""),
                "csrftoken": cookie.get("csrftoken", ""),
            }
        )
    ]


# ---------------------------------------------------------------- classes
def _import_classes(base_dir: Path) -> None:
    from context import DEFAULT_RANKING_METHOD, DraftClassContext
    from drafted_players import save_drafted_info

    league_ids = {r["id"] for r in db.query("SELECT id FROM leagues")}
    for dataset in sorted((base_dir / "datasets").glob("*.csv")):
        name = dataset.stem
        folder = base_dir / "processed_classes" / name
        config = _read_json(folder / "config.json")
        config = config if isinstance(config, dict) else {}
        # a pin to a league that no longer exists behaved as unassigned
        league_id = config.get("league_id") if config.get("league_id") in league_ids else None
        saved = _read_json(folder / "custom_ranking.json")
        order = saved.get("order") if isinstance(saved, dict) else None
        db.execute(
            "INSERT INTO draft_classes (name, ranking_method, print_method, league_id, "
            "custom_order) VALUES (?, ?, ?, ?, ?)",
            (
                name,
                config.get("ranking_method") or DEFAULT_RANKING_METHOD,
                config.get("print_method") or "draft_prospects",
                league_id,
                json.dumps([str(p) for p in order]) if isinstance(order, list) else None,
            ),
        )
        drafted = _drafted_info(DraftClassContext(name), folder / "drafted_players.csv")
        if drafted:
            save_drafted_info(DraftClassContext(name), drafted)
        method = config.get("ranking_method") or DEFAULT_RANKING_METHOD
        # the app only ever served the current method's file, fresh or not
        _import_run(results_store.CLASS, name, method, 1, folder / _ranker_dir(method))


def _drafted_info(ctx, path: Path) -> dict:
    from drafted_players import resolve_selection_rows

    if not path.exists():
        return {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = [(n or "").strip().lower() for n in (reader.fieldnames or [])]
        rows = list(reader)
    if "id" not in fieldnames:
        return resolve_selection_rows(ctx, rows)
    drafted = {}
    for row in rows:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        pid = norm.get("id")
        if pid:
            drafted[pid] = {
                "name": norm.get("name", ""),
                "team": norm.get("team", ""),
                "round": norm.get("round", ""),
                "round_selection": norm.get("pick", ""),
                "overall_selection": norm.get("overall", ""),
            }
    return drafted


# -------------------------------------------------------------- snapshots
def _import_snapshots(base_dir: Path) -> None:
    league_ids = {r["id"] for r in db.query("SELECT id FROM leagues")}
    root = base_dir / "league_snapshots"
    if not root.is_dir():
        return
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = _read_json(folder / "meta.json")
        if folder.name not in league_ids or not isinstance(meta, dict):
            continue
        for method in ("overall", "potential"):
            ranked = folder / _ranker_dir(method) / "ranked_players.csv"
            # the old app re-scored a ranking older than the snapshot it came from
            if ranked.exists() and _mtime(ranked) >= _mtime(folder / "players.csv"):
                _import_run(results_store.LEAGUE, folder.name, method, 1, ranked.parent)
        db.execute(
            "INSERT INTO league_snapshots (league_id, fetched_at, last_checked_at, "
            "player_count, total_row_count, league_date) VALUES (?, ?, ?, ?, ?, ?)",
            (
                folder.name, meta.get("fetched_at"), meta.get("last_checked_at"),
                meta.get("player_count"), meta.get("total_row_count"), meta.get("league_date"),
            ),
        )


# ----------------------------------------------------------- trade lists
def import_trade_lists(base_dir) -> None:
    """trade_lists.json - `{league_id: [{id, name, createdAt, entries: [...]}]}` -
    into the trade-list tables (`db._migration_2`). Lists of a league that no
    longer exists are dropped, as deleting the league would have done."""
    data = _read_json(Path(base_dir) / "trade_lists.json")
    if not isinstance(data, dict):
        return
    known = {r["id"] for r in db.query("SELECT id FROM leagues")}
    with db.transaction() as conn:
        for league_id, lists in data.items():
            if league_id not in known or not isinstance(lists, list):
                continue
            for lst in lists:
                if not isinstance(lst, dict) or not lst.get("id"):
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO trade_lists (league_id, id, name, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (league_id, lst["id"], lst.get("name") or lst["id"], lst.get("createdAt")),
                )
                for e in lst.get("entries") or []:
                    if not isinstance(e, dict) or not e.get("playerId"):
                        continue
                    # the file's first entry for a player is the one the app used
                    conn.execute(
                        "INSERT OR IGNORE INTO trade_list_entries (league_id, list_id, "
                        "player_id, priority, note, added_at, name, position, org) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            league_id, lst["id"], str(e["playerId"]), e.get("priority"),
                            e.get("note") or "", e.get("addedAt"), e.get("name") or "",
                            e.get("position") or "", e.get("org") or "",
                        ),
                    )


# ------------------------------------------------------------- rankings
def _mtime(path: Path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _ranker_dir(method: str) -> str:
    from rankers.get_ranker import RANKERS

    return RANKERS[method].__name__


# ranked_players.csv columns -> result-row keys, all numeric except these
_TEXT_COLUMNS = {"id", "name", "position", "best_position", "demand"}
_RESULT_COLUMNS = (
    "id", "name", "position", "age", "model_score", "raw_overall_score",
    "position_player_score", "batting_score_component", "fielding_score_component",
    "running_score_component", "best_position", "pitcher_score", "starter_component",
    "reliever_component", "in_game_overall", "in_game_potential", "demand",
)


def _number(text):
    """A CSV cell back to the int / float it was written from ("" -> None)."""
    if text is None or text == "":
        return None
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def _import_run(scope, scope_id, method, source_version, folder: Path) -> None:
    path = folder / "ranked_players.csv"
    if not path.exists():
        return
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    results = []
    for row in rows:
        result = {
            col: (row.get(col) or "") if col in _TEXT_COLUMNS else _number(row.get(col))
            for col in _RESULT_COLUMNS
        }
        result["player_type"] = classify(
            result["position_player_score"], result["pitcher_score"]
        )
        result["breakdown"] = prune_breakdown(
            legacy_breakdown(row.get("components")), result["player_type"]
        )
        results.append(result)
    scored_at = datetime.fromtimestamp(_mtime(path), tz=timezone.utc).isoformat()
    results_store.save_run(scope, scope_id, method, source_version, results, scored_at)


# old `components` key -> breakdown path (see scoring/runtime_components.py)
_LEGACY_PATHS = {
    "Pos - Batting Model": "batting.model.batting",
    "Pos - Running Model": "batting.model.running",
    "Pos - Overall Model Score": "batting.model.overall",
    "Pos - Utility Bonus": "batting.model.utility_bonus",
    "Total Pos Modifier": "batting.modifier_total",
    "Total Pitcher Modifier": "pitching.modifier_total",
    "SP Model Score": "pitching.starter.model",
    "SP Base Modifier": "pitching.starter.base_modifier",
    "SP Pitcher Pitch Component": "pitching.starter.pitch_mix",
    "SP HR component": "pitching.starter.hr_risk",
    "Starter Score w/Modifiers": "pitching.starter.score",
    "RP Model Score": "pitching.reliever.model",
    "RP Base Modifier": "pitching.reliever.base_modifier",
    "Reliever Score w/Modifiers": "pitching.reliever.score",
    "Pre Rank-adj Rank": "rank_adjust.pre_rank",
    "Pre Rank-adj Score": "rank_adjust.pre_score",
}
_LEGACY_PREFIXES = (
    ("Pos Modifier ", "batting.modifiers."),
    ("Pitcher Modifier ", "pitching.modifiers."),
    ("Rank-adj Modifier ", "rank_adjust.modifiers."),
)
_BEST_POSITION_RE = re.compile(r"^Pos - Best Pos Score \(\w+\)$")
# keys from older pipeline versions with no place in the breakdown, by side
_LEGACY_PITCHING = ("Pitcher", "Pre-Pitcher", "SP ", "RP ", "Starter", "Reliever")
# NumPy >= 2 renders scalars as `np.float64(1.02)` in a dict's repr - a call,
# not a literal - and some files have those baked into the column.
_NP_SCALAR_RE = re.compile(r"np\.\w+\(([^()]*)\)")


def _parse_components(raw) -> dict:
    if not raw:
        return {}
    for candidate in (raw, _NP_SCALAR_RE.sub(r"\1", raw)):
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(candidate)
            except (ValueError, SyntaxError):
                continue
            return parsed if isinstance(parsed, dict) else {}
    return {}


def legacy_breakdown(raw) -> dict:
    """An old stringified `components` dict as a nested score breakdown. Keys an
    older pipeline wrote that have no place in it land in a `legacy` map on the
    side they belong to (still pruned by player type), else at the top."""
    tree = {}
    for key, value in _parse_components(raw).items():
        path = _LEGACY_PATHS.get(key)
        if path is None and _BEST_POSITION_RE.match(key):
            path = "batting.model.best_position_score"
        for prefix, target in _LEGACY_PREFIXES:
            if path is None and key.startswith(prefix):
                path = target + key[len(prefix):]
        if path is not None:
            set_path(tree, path, value)
        elif key.startswith("Pos"):
            tree.setdefault("batting", {}).setdefault("legacy", {})[key] = value
        elif key.startswith(_LEGACY_PITCHING):
            tree.setdefault("pitching", {}).setdefault("legacy", {})[key] = value
        else:
            tree.setdefault("legacy", {})[key] = value
    return tree
