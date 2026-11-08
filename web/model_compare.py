"""The Compare view: every player's overall score and rank under each ranking
engine side by side, for a draft class or a league snapshot.

Each engine's rows come from the same loaders the ranked tables use (scoring a
run that engine hasn't made yet). Ranks are each engine's own model order, not
a class's custom order. The engines' units differ - legacy points against v2's
50 + 10 x WAR - so the score diff is only a rough guide; the rank diff is the
like-for-like comparison.
"""
import ranking_engine
from web import service
from web.service import InvalidInput

# sortable fields -> row key
SORT_FIELDS = {
    "v2Rank": "v2_rank", "legacyRank": "legacy_rank", "rankDiff": "rank_diff",
    "v2Score": "v2_score", "legacyScore": "legacy_score", "scoreDiff": "score_diff",
    "name": "name", "age": "age", "position": "position",
}


def _class_rows(name: str) -> list:
    ctx = service._ctx(name)
    rows = service._read_ranked_rows(ctx)
    if rows is None:
        raise InvalidInput(f"Draft class {name!r} hasn't been processed yet.")
    return [
        {"id": r["id"], "name": r["name"], "position": r["position"], "age": service._to_int(r.get("age")),
         "org": None, "level": None, "player_type": r.get("player_type"),
         "score": service._to_number(r.get("model_score")), "rank": i + 1}
        for i, r in enumerate(rows)
    ]


def _league_rows(league_id: str, method: str) -> list:
    return [
        {"id": r["id"], "name": r["name"], "position": r["position"], "age": r["age"], "org": r["org"],
         "level": r["level"], "player_type": r["type"], "score": r["model_score"], "rank": r["rank"]}
        for r in service._league_built_rows(league_id, method)
    ]


def comparison_rows(class_name=None, league_id=None, method="overall") -> list:
    """One row per player in either engine's ranking, in v2 order."""
    if bool(class_name) == bool(league_id):
        raise InvalidInput("Compare one draft class or one league.")
    by_engine = {}
    for engine in ranking_engine.ENGINES:
        with ranking_engine.using(engine):
            rows = _class_rows(class_name) if class_name else _league_rows(league_id, method)
        by_engine[engine] = {r["id"]: r for r in rows}
    v2, legacy = by_engine["v2"], by_engine["legacy"]
    out = []
    for pid in list(v2) + [p for p in legacy if p not in v2]:
        new, old = v2.get(pid), legacy.get(pid)
        base = new or old
        row = {k: base[k] for k in ("id", "name", "position", "age", "org", "level")}
        row["player_type"] = (new or old)["player_type"]
        row["v2_score"], row["v2_rank"] = (new["score"], new["rank"]) if new else (None, None)
        row["legacy_score"], row["legacy_rank"] = (old["score"], old["rank"]) if old else (None, None)
        both = new and old
        row["score_diff"] = new["score"] - old["score"] if both and None not in (new["score"], old["score"]) else None
        row["rank_diff"] = old["rank"] - new["rank"] if both else None
        out.append(row)
    return out


def model_comparison_page(
    *, class_name=None, league_id=None, method="overall", search=None, positions=None, level=None,
    sort=None, page=0, page_size=100,
):
    rows = comparison_rows(class_name, league_id, method)
    if search:
        needle = search.strip().lower()
        rows = [r for r in rows if needle in (r["name"] or "").lower() or needle in (r["org"] or "").lower()]
    if positions:
        wanted = set(positions)
        rows = [r for r in rows if r["position"] in wanted]
    if level:
        rows = [r for r in rows if r["level"] == level]
    if sort:
        key = SORT_FIELDS.get(sort.get("field"))
        if key is None:
            raise InvalidInput(f"Can't sort the comparison by {sort.get('field')!r}.")
        order = sort.get("order") or 1
        present = [r for r in rows if r[key] is not None]
        missing = [r for r in rows if r[key] is None]
        present.sort(key=lambda r: r[key], reverse=order < 0)
        rows = present + missing  # blanks last either way
    total = len(rows)
    start = max(page, 0) * page_size
    return {"rows": rows[start:start + page_size], "total_records": total}
