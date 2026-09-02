"""End-to-end processing for one draft class, importable and context-driven.

    process_class(ctx)
      -> normalise the dataset CSV headers
      -> load GamePlayer rows
      -> rank + write <Ranker>/eval_model.csv
      -> write <Ranker>/ranked_players.csv + upload_ranked_players.csv
"""
import csv

import ranking_csv
from context import DraftClassContext
from draft_class_files import get_draft_class_data_file, get_draft_class_eval_model_file
from models.game_players import GamePlayer
from rankers.get_ranker import get_ranker

EVAL_MODEL_FIELDNAMES = [
    "ranking",
    "id",
    "name",
    "position",
    "age",
    "position_player_score",
    "fielding_score_component",
    "batting_score_component",
    "pitcher_score",
    "starter_component",
    "reliever_component",
    "overall_score",
    "in_game_potential",
    "demand",
    "raw_overall_score",
    "components",
]


def normalise_dataset(ctx) -> None:
    """OOTP exports the pitching control column with the same header as batting
    contact ("CON P" / "CON"); rename so both are readable."""
    path = get_draft_class_data_file(ctx)
    with open(path, newline="") as f:
        filedata = f.read()

    fixed = filedata
    if "MOV P,CON P" in fixed:
        fixed = fixed.replace("MOV P,CON P", "MOV P,CONT P")
    if "MOV,CON," in fixed:
        fixed = fixed.replace("MOV,CON,", "MOV,CONT,")

    if fixed != filedata:
        with open(path, "w", newline="") as f:
            f.write(fixed)


def load_player_data(ctx) -> list:
    with open(get_draft_class_data_file(ctx), newline="") as csvfile:
        return [GamePlayer(row) for row in csv.DictReader(csvfile)]


def write_player_scores(ctx, players) -> None:
    players_by_id = {player.id: player for player in players}
    ranker = get_ranker(ctx)
    player_scores = ranker.rank(players)
    with open(get_draft_class_eval_model_file(ranker, ctx), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=EVAL_MODEL_FIELDNAMES)
        writer.writeheader()
        for i, score in enumerate(player_scores):
            player = players_by_id[score.id]
            writer.writerow(
                {
                    "ranking": i,
                    "id": player.id,
                    "name": player.name,
                    "position": player.position,
                    "age": player.age,
                    "position_player_score": score.position_player_score,
                    "fielding_score_component": score.fielding_score_component,
                    "batting_score_component": score.batting_score_component,
                    "pitcher_score": score.pitcher_score,
                    "starter_component": score.starter_component,
                    "reliever_component": score.reliever_component,
                    "overall_score": round(score.overall_score, 2),
                    "in_game_potential": player.potential,
                    "demand": player.demand,
                    "raw_overall_score": score.raw_overall_score,
                    "components": score.components,
                }
            )


def process_class(ctx) -> None:
    ctx.ensure_dirs()
    normalise_dataset(ctx)
    players = load_player_data(ctx)
    write_player_scores(ctx, players)
    ranking_csv.create_ranking_csv(ctx)


if __name__ == "__main__":
    from constants import DRAFT_CLASS_NAME

    ctx = DraftClassContext(DRAFT_CLASS_NAME)
    print(f"Running evals for {DRAFT_CLASS_NAME}!")
    process_class(ctx)
