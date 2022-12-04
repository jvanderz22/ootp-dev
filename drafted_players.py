import csv

from constants import DRAFTED_PLAYERS_FILE_PATH


def get_drafted_player_ids():
    players_by_name = {}
    with open("./processed_data/eval_model.csv", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for player in reader:
            name = player["name"].lower()
            players_by_name[name] = player

    drafted_player_id_set = set()
    with open(DRAFTED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, drafted_player in enumerate(reader):
            player_data = drafted_player["Selection"]
            player_name_arr = player_data.split(" ")[1:]
            if len(player_name_arr[-1]) == 1:
                player_name_arr = player_name_arr[0:-1]
            player_name = " ".join(player_name_arr).lower()
            player = players_by_name[player_name]
            drafted_player_id_set.add(player["id"])
    return drafted_player_id_set
