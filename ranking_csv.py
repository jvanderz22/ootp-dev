"""Turn the raw eval_model.csv into the ranked_players.csv view and the
upload_ranked_players.csv file used for the StatsPlus / C+ preference list.

The upload file always reflects the saved custom order (custom_ranking.py) and
excludes players already drafted (drafted_players.py).
"""
import csv

from custom_ranking import resolve_order
from draft_class_files import get_draft_class_eval_model_file, get_ranked_players_file
from drafted_players import get_drafted_player_ids
from rankers.get_ranker import get_ranker

RANKED_PLAYER_FIELDNAMES = [
    "overall_ranking",
    "model_ranking",
    "ranking_difference",
    "id",
    "name",
    "position",
    "age",
    "model_score",
    "position_player_score",
    "fielding_score_component",
    "batting_score_component",
    "pitcher_score",
    "starter_component",
    "reliever_component",
    "running_score_component",
    "in_game_overall",
    "in_game_potential",
    "demand",
    "raw_overall_score",
    "components",
]

UPLOAD_FIELDNAMES = ["id", "name", "position", "age", "model_score", "demand"]
UPLOAD_LIMIT = 500


def _read_eval_model(ctx, ranker):
    with open(get_draft_class_eval_model_file(ranker, ctx), newline="") as csvfile:
        rows = list(csv.DictReader(csvfile))
    seen = set()
    deduped = []
    for row in rows:
        if row["id"] not in seen:
            seen.add(row["id"])
            deduped.append(row)
    return deduped


def _ranked_row(index, player):
    model_ranking = int(player["ranking"])
    return {
        "overall_ranking": index,
        "model_ranking": model_ranking,
        "ranking_difference": index - model_ranking,
        "id": player["id"],
        "name": player["name"],
        "position": player["position"],
        "age": player["age"],
        "model_score": player["overall_score"],
        "position_player_score": player["position_player_score"],
        "fielding_score_component": player["fielding_score_component"],
        "batting_score_component": player["batting_score_component"],
        "pitcher_score": player["pitcher_score"],
        "starter_component": player["starter_component"],
        "reliever_component": player["reliever_component"],
        "running_score_component": player["running_score_component"],
        "in_game_overall": player["in_game_overall"],
        "in_game_potential": player["in_game_potential"],
        "demand": player["demand"],
        "raw_overall_score": player["raw_overall_score"],
        "components": player["components"],
    }


def create_ranking_csv(ctx=None):
    if ctx is None:
        from constants import DRAFT_CLASS_NAME
        from context import DraftClassContext

        ctx = DraftClassContext(DRAFT_CLASS_NAME)

    ranker = get_ranker(ctx)
    model_ranked_players = _read_eval_model(ctx, ranker)

    with open(get_ranked_players_file(ranker, ctx), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RANKED_PLAYER_FIELDNAMES)
        writer.writeheader()
        for i, player in enumerate(model_ranked_players):
            writer.writerow(_ranked_row(i, player))

    write_upload_file(ctx)


def build_upload_rows(ctx):
    """Rows for the C+ upload CSV: resolved (custom) order, drafted excluded,
    capped at UPLOAD_LIMIT. Reads ranked_players.csv so it stays in sync with the
    latest custom order even if the class has not been reprocessed."""
    ranker = get_ranker(ctx)
    with open(get_ranked_players_file(ranker, ctx), newline="") as csvfile:
        ranked = list(csv.DictReader(csvfile))

    ordered = resolve_order(ctx, ranked)
    drafted = get_drafted_player_ids(ctx)

    rows = []
    for player in ordered:
        if player["id"] in drafted:
            continue
        rows.append(
            {
                "id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "age": player["age"],
                "model_score": player["model_score"],
                "demand": player["demand"],
            }
        )
        if len(rows) >= UPLOAD_LIMIT:
            break
    return rows


def write_upload_file(ctx) -> None:
    ctx.processed_dir.mkdir(parents=True, exist_ok=True)
    with open(ctx.upload_players_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=UPLOAD_FIELDNAMES)
        for row in build_upload_rows(ctx):
            writer.writerow(row)


if __name__ == "__main__":
    create_ranking_csv()
