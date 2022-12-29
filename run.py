import potential_eval_model
import ranking_csv
from constants import DATASET_FILE_PATH


def process_file():
    with open(DATASET_FILE_PATH, newline="") as file:
        filedata = file.read()
    has_duplicate_con_p = filedata.find("MOV P,CON P")

    if has_duplicate_con_p:
        # Replace duplicate CON P field. Pitching control field needs to be CONT P instead of CON P
        filedata = filedata.replace("MOV P,CON P", "MOV P,CONT P")
        with open(DATASET_FILE_PATH, "w") as file:
            file.write(filedata)


if __name__ == "__main__":
    process_file()
    potential_eval_model.score_players(DATASET_FILE_PATH)
    ranking_csv.create_ranking_csv()
