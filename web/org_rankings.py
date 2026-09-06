"""Rank every org's farm system against each other, using the potential model.

The scoring pieces here are the pure core of `print_org_summaries.py`: a steeply
convex points curve (a handful of elite prospects outweigh org depth) plus a
per-org rollup. `print_org_summaries.py` imports `ORG_POINTS_MODEL` from here so
the curve lives in one place; `web.service.league_org_rankings` feeds
`summarize_orgs` the already-built live-league rows.
"""
from utils.rank_graditated_model import RankGradiatedModel

# Somewhere between 58 and 60 is the minimum model_score worth any org value;
# the curve then ramps hard so the top of a system dominates its score.
ORG_POINTS_MODEL = RankGradiatedModel(
    [0, 58, 62, 65, 68, 70, 72, 75, 80, 85, 90, 100, 110, 120],
    [0, 0, 2.2, 6, 9, 11, 14, 19, 32, 45, 61, 81, 92, 100],
)

# Global-rank cutoffs for the tier-count line. The CLI compared a 0-based
# `overall_ranking < N`; the web rows carry a 1-based `rank`, so the equivalent
# threshold is `rank <= N`.
_TIERS = (10, 50, 100, 250, 500)


def _model_score(row) -> float:
    try:
        return float(row.get("model_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _org_name(rows) -> str:
    for r in rows:
        if r.get("org"):
            return r["org"]
    return rows[0].get("org_id") or ""


def summarize_orgs(rows, *, top_n: int = 25) -> list[dict]:
    """Roll built live-league rows up per parent org, best system first.

    `rows` are `web.service._league_built_rows` payloads (they carry `org_id`,
    `org`, `rank`, `model_score`). Each result dict:

    - `org_score`   sum of `ORG_POINTS_MODEL.rank(model_score)` over the org
    - `top10..top500` count of rows with `rank <= N`
    - `prospect_count` rows in the org
    - `top_prospects` the first `top_n` rows, best-first (raw player payloads)
    """
    by_org: dict[str, list] = {}
    for r in rows:
        org_id = str(r.get("org_id") or "").strip()
        # "" / "0" == free agents and other unaffiliated players (see `_is_org`
        # in web/service.py) - not a farm system.
        if not org_id or org_id == "0":
            continue
        by_org.setdefault(org_id, []).append(r)

    out = []
    for org_id, org_rows in by_org.items():
        ordered = sorted(org_rows, key=_model_score, reverse=True)
        summary = {
            "org_id": org_id,
            "org_name": _org_name(ordered),
            "org_score": sum(ORG_POINTS_MODEL.rank(_model_score(r)) for r in ordered),
            "prospect_count": len(ordered),
            "top_prospects": ordered[:top_n],
        }
        for tier in _TIERS:
            summary[f"top{tier}"] = sum(
                1 for r in ordered if (r.get("rank") or 0) <= tier
            )
        out.append(summary)

    out.sort(key=lambda s: s["org_score"], reverse=True)
    return out
