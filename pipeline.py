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
    "running_score_component",
    "overall_score",
    "in_game_overall",
    "in_game_potential",
    "demand",
    "raw_overall_score",
    "components",
]


# The pitching-control columns collide with the batting "CON" / "CON P" headers
# in an OOTP export. Older exports reuse those headers verbatim; newer ones
# duplicate them and the CSV writer de-dupes the second copy to "CON_1" /
# "CONT P_1". Either way we want them as "CONT" (current) and "CONT P" (potential).
_CONTROL_ALIASES = {
    "CON_1": "CONT",
    "CON P_1": "CONT P",
    "CONT P_1": "CONT P",
}


def normalise_dataset(ctx) -> None:
    """Rewrite the header row so the pitching-control columns read as
    "CONT" / "CONT P", regardless of which collision form the export used."""
    path = get_draft_class_data_file(ctx)
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    original = list(header)

    def present():
        return {h.strip() for h in header}

    # Explicit de-duped aliases: "CON_1" -> "CONT", "CONT P_1" -> "CONT P", ...
    for i, col in enumerate(header):
        target = _CONTROL_ALIASES.get(col.strip())
        if target and target not in present():
            header[i] = target

    # Older form: the pitching block is STU, MOV, CON, STU P, MOV P, CON P - the
    # control columns sit right after MOV / MOV P and are still literally "CON".
    for anchor, target in (("MOV", "CONT"), ("MOV P", "CONT P")):
        if target in present():
            continue
        try:
            j = header.index(anchor) + 1
        except ValueError:
            continue
        if j < len(header) and header[j].strip() in ("CON", "CON P"):
            header[j] = target

    if header != original:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerows(rows)


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
                    "running_score_component": score.running_score_component,
                    "overall_score": round(score.overall_score, 2),
                    "in_game_overall": player.overall,
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
