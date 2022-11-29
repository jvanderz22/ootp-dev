import potential_eval_model
import ranking_csv

player_dataset = {"file_path": "./datasets/2029-yfmlb-draft-class.csv"}


def process_file():
    with open(player_dataset["file_path"], newline="") as file:
        filedata = file.read()
    has_duplicate_con_p = filedata.find("MOV P,CON P")

    if has_duplicate_con_p:
        # Replace duplicate CON P field. Pitching control field needs to be CONT P instead of CON P
        filedata = filedata.replace("MOV P,CON P", "MOV P,CONT P")
        with open(player_dataset["file_path"], "w") as file:
            file.write(filedata)


if __name__ == "__main__":
    process_file()
    potential_eval_model.score_players(player_dataset["file_path"])
    ranking_csv.create_ranking_csv()
