"""Rank every org's farm system against each other, using the potential model.

The scoring pieces here are the pure core of `print_org_summaries.py`: a steeply
convex points curve (a handful of elite prospects outweigh org depth) plus a
per-org rollup. `print_org_summaries.py` imports `ORG_POINTS_MODEL` from here so
the curve lives in one place; `web.service.league_org_rankings` feeds
`summarize_orgs` the already-built live-league rows.

Under v2 a row's score is 50 + 10 x potential WAR, so the curve is read in WAR
(`ORG_WAR_MODEL`).
"""
from ranking.value import DISPLAY_OFFSET, DISPLAY_SCALE
from utils.rank_graditated_model import RankGradiatedModel

# Somewhere between 58 and 60 is the minimum model_score worth any org value;
# the curve then ramps hard so the top of a system dominates its score.
ORG_POINTS_MODEL = RankGradiatedModel(
    [0, 58, 62, 65, 68, 70, 72, 75, 80, 85, 90, 100, 110, 120],
    [0, 0, 2.2, 6, 9, 11, 14, 19, 32, 45, 61, 81, 92, 100],
)
# The same curve in potential WAR, for v2 (2026-11-09; plans/xgboost-phaseout-plan.md,
# step 3): each breakpoint is the WAR at the same percentile of the live league's
# v2 potential board as its points were of legacy's (yfmlb, 2042-11-07) - 58
# points was the top 3.6%, +3.9 WAR. 110 is smoothed: only 3 players reached it.
ORG_WAR_MODEL = RankGradiatedModel(
    [0, 3.9, 4.3, 4.6, 4.9, 5.1, 5.3, 5.6, 6.0, 6.4, 7.1, 8.1, 8.8, 9.6],
    ORG_POINTS_MODEL.vals,
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


def org_points(model_score, engine: str = "legacy") -> float:
    """What one prospect adds to his org's score, from his `engine` score."""
    if engine == "v2":
        return ORG_WAR_MODEL.rank((model_score - DISPLAY_OFFSET) / DISPLAY_SCALE)
    return ORG_POINTS_MODEL.rank(model_score)


def summarize_orgs(rows, *, top_n: int = 25, engine: str = "legacy") -> list[dict]:
    """Roll built live-league rows up per parent org, best system first.

    `rows` are `web.service._league_built_rows` payloads (they carry `org_id`,
    `org`, `rank`, `model_score`), scored by `engine`. Each result dict:

    - `org_score`   sum of `org_points(model_score)` over the org
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
            "org_score": sum(org_points(_model_score(r), engine) for r in ordered),
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
