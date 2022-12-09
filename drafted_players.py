import csv

from constants import DRAFTED_PLAYERS_FILE_PATH


def get_drafted_player_ids():
    players_by_name = {}
    with open("./processed_data/eval_model.csv", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for player in reader:
            name = player["name"].lower()
            position = player["position"].lower()
            if position == "sp" or position == "rp" or position == "cl":
                position = "p"
            if players_by_name.get(name) is None:
                players_by_name[name] = {position: player}
            else:
                players_by_name[name][position] = player

    drafted_player_id_set = set()
    with open(DRAFTED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, drafted_player in enumerate(reader):
            player_data = drafted_player["Selection"].split(" ")
            player_name_arr = player_data[1:]
            if len(player_name_arr[-1]) == 1:
                player_name_arr = player_name_arr[0:-1]
            player_name = " ".join(player_name_arr).lower()
            player_position = player_data[0].lower()
            player = players_by_name[player_name][player_position]
            drafted_player_id_set.add(player["id"])
    return drafted_player_id_set
