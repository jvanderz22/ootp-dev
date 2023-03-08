import os
import csv

import potential_eval_model
import ranking_csv
from constants import DRAFT_CLASS_NAME
from draft_class_files import (
    get_draft_class_data_file,
    get_draft_class_drafted_players_file,
)
from print_pos_distribution import print_top_distribution


def process_file():
    with open(get_draft_class_data_file(), newline="") as file:
        filedata = file.read()
    has_duplicate_con_p = filedata.find("MOV P,CON P")

    if has_duplicate_con_p:
        # Replace duplicate CON P field. Pitching control field needs to be CONT P instead of CON P
        filedata = filedata.replace("MOV P,CON P", "MOV P,CONT P")

        with open(get_draft_class_data_file(), "w", newline="") as file:
            file.write(filedata)


if __name__ == "__main__":
    # Create a directory to store info about the draft class if it doesn't exist
    if not os.path.exists(f"processed_classes/{DRAFT_CLASS_NAME}"):
        os.makedirs(f"processed_classes/{DRAFT_CLASS_NAME}")
        with open(get_draft_class_drafted_players_file(), "w", newline="") as file:
            header = ["Round", "Pick", "Overall", "Team", "Player", "Time"]
            writer = csv.DictWriter(file, fieldnames=header)
            writer.writeheader()
    print(f"Running evals for {DRAFT_CLASS_NAME}!")

    process_file()
    potential_eval_model.score_players()
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
