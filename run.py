import os
import csv

from models.game_players import GamePlayer
from rankers.get_ranker import get_ranker
import ranking_csv
from constants import DRAFT_CLASS_NAME
from draft_class_files import (
    get_draft_class_data_file,
    get_draft_class_drafted_players_file,
)
from print_pos_distribution import print_top_distribution
from draft_class_files import (
    get_draft_class_eval_model_file,
)


def process_file():
    with open(get_draft_class_data_file(), newline="") as file:
        filedata = file.read()
    has_duplicate_con_p = filedata.find("MOV P,CON P")
    has_duplicate_con = filedata.find("MOV,CON")

    if has_duplicate_con_p:
        # Replace duplicate CON P field. Pitching control field needs to be CONT P instead of CON P
        filedata = filedata.replace("MOV P,CON P", "MOV P,CONT P")

        with open(get_draft_class_data_file(), "w", newline="") as file:
            file.write(filedata)
    if has_duplicate_con:
        # Replace duplicate CON field. Pitching control field needs to be CONT instead of CON
        filedata = filedata.replace("MOV,CON,", "MOV,CONT,")

        with open(get_draft_class_data_file(), "w", newline="") as file:
            file.write(filedata)


def write_player_scores_to_file(players):
    output_field_names = [
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
    ]

    all_players_by_id = {player.id: player for player in players}
    ranker = get_ranker()
    player_scores = ranker.rank(players)
    with open(get_draft_class_eval_model_file(ranker), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=output_field_names)
        writer.writeheader()
        for i, player_score in enumerate(player_scores):
            player = all_players_by_id[player_score.id]
            writer.writerow(
                {
                    "ranking": i,
                    "id": player.id,
                    "name": player.name,
                    "position": player.position,
                    "age": player.age,
                    "position_player_score": player_score.position_player_score,
                    "fielding_score_component": player_score.fielding_score_component,
                    "batting_score_component": player_score.batting_score_component,
                    "pitcher_score": player_score.pitcher_score,
                    "starter_component": player_score.starter_component,
                    "reliever_component": player_score.reliever_component,
                    "overall_score": round(player_score.overall_score, 2),
                    "in_game_potential": player.potential,
                    "demand": player.demand,
                    "raw_overall_score": player_score.raw_overall_score,
                }
            )


def load_player_data():
    players = []
    with open(get_draft_class_data_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, player in enumerate(reader):
            game_player = GamePlayer(player)
            players.append(game_player)
    return players


if __name__ == "__main__":
    # Create a directory to store info about the draft class if it doesn't exist
    if not os.path.exists(f"processed_classes/{DRAFT_CLASS_NAME}"):
        os.makedirs(f"processed_classes/{DRAFT_CLASS_NAME}")
    if not os.path.exists(get_draft_class_data_file()):
        with open(get_draft_class_drafted_players_file(), "w", newline="") as file:
            header = ["Round", "Pick", "Overall", "Team", "Player", "Time"]
            writer = csv.DictWriter(file, fieldnames=header)
            writer.writeheader()

    print(f"Running evals for {DRAFT_CLASS_NAME}!")
    process_file()
    players = load_player_data()
    write_player_scores_to_file(players)
    ranking_csv.create_ranking_csv()

    print_top_distribution(10)
    print("\n\n\n")
    print_top_distribution(20)
    print("\n\n\n")
    print_top_distribution(50)
    print("\n\n\n")
    print_top_distribution(100)
    print("\n\n\n")
    print_top_distribution(400)
    print("\n\n\n")
    print_top_distribution(1000)
