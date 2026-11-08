"""The Compare view's columns: every player's overall score and rank under each
ranking engine, added to the ranked table's rows (a draft class's or a league
snapshot's) when the table asks for them.

Each engine's rows come from the same loaders the ranked tables use (scoring a
run that engine hasn't made yet). Ranks are each engine's own model order, not
a class's custom order. The engines' units differ - legacy points against v2's
50 + 10 x WAR - so the score diff is only a rough guide; the rank diff is the
like-for-like comparison.
"""
import ranking_engine
from web import service

FIELDS = ("legacy_score", "legacy_rank", "v2_score", "v2_rank", "score_diff", "rank_diff")


def _class_rows(name: str) -> list:
    rows = service._read_ranked_rows(service._ctx(name)) or []
    return [{"id": r["id"], "score": service._to_number(r.get("model_score")), "rank": i + 1}
            for i, r in enumerate(rows)]


def _league_rows(league_id: str, method: str) -> list:
    return [{"id": r["id"], "score": r["model_score"], "rank": r["rank"]}
            for r in service._league_built_rows(league_id, method)]


def comparison(class_name=None, league_id=None, method="overall") -> dict:
    """{player id: the comparison fields} for one class or one league ranking."""
    by_engine = {}
    for engine in ranking_engine.ENGINES:
        with ranking_engine.using(engine):
            rows = _class_rows(class_name) if class_name else _league_rows(league_id, method)
        by_engine[engine] = {r["id"]: r for r in rows}
    v2, legacy = by_engine["v2"], by_engine["legacy"]
    out = {}
    for pid in set(v2) | set(legacy):
        new, old = v2.get(pid), legacy.get(pid)
        both = new is not None and old is not None
        scored = both and None not in (new["score"], old["score"])
        out[pid] = {
            "v2_score": new and new["score"], "v2_rank": new and new["rank"],
            "legacy_score": old and old["score"], "legacy_rank": old and old["rank"],
            "score_diff": new["score"] - old["score"] if scored else None,
            "rank_diff": old["rank"] - new["rank"] if both else None,
        }
    return out


def with_comparison(rows: list, **which) -> list:
    """Copies of `rows` (ranked-table payloads) with the comparison fields."""
    fields = comparison(**which)
    blank = dict.fromkeys(FIELDS)
    return [{**r, **fields.get(r["id"], blank)} for r in rows]
