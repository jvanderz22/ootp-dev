import csv
import os

from draft_class_files import (
    get_draft_class_drafted_players_file,
)
from get_game_players import get_game_players


def get_drafted_player_ids():
    # return get_drafted_player_ids_in_game()
    return get_drafted_players_stats_plus().keys()


def get_drafted_players_info():
    return get_drafted_players_stats_plus()


def get_drafted_players_stats_plus():
    players_by_name = {}
    game_players = get_game_players().game_players
    for player in game_players:
        name = player.name.lower()
        position = player.position.lower()
        if position == "sp" or position == "rp" or position == "cl":
            position = "p"
        if players_by_name.get(name) is None:
            players_by_name[name] = {position: player}
        else:
            players_by_name[name][position] = player

    drafted_players = {}
    if not os.path.exists(get_draft_class_drafted_players_file()):
        return drafted_players

    with open(get_draft_class_drafted_players_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, drafted_player in enumerate(reader):
            player_data = drafted_player["Selection"].split(" ")
            player_name_arr = player_data[1:]
            if len(player_name_arr) < 1:
                continue
            if len(player_name_arr[-1]) == 1:
                player_name_arr = player_name_arr[0:-1]
            player_name = " ".join(player_name_arr).lower()
            player_position = player_data[0].lower()
            player = players_by_name.get(player_name, {}).get(player_position)
            if player is None:
                player_obj = players_by_name.get(player_name)
                if player_obj is not None:
                    player = list(player_obj.values())[0]
            # TODO not sure this is working

            if player is not None:
                drafted_players[player.id] = {
                    "name": player_name,
                    "team": drafted_player["Team"],
                    "round": drafted_player["Round"],
                    "round_selection": drafted_player["Pick"],
                    "overall_selection": drafted_player["Overall"],
                }
    return drafted_players


def get_drafted_player_ids_in_game():
    players_by_name = {}
    game_players = get_game_players().game_players
    for player in game_players:
        name = player.name.lower()
        position = player.position.lower()
        if position == "sp" or position == "rp" or position == "cl":
            position = "p"
        if players_by_name.get(name) is None:
            players_by_name[name] = {position: player}
        else:
            players_by_name[name][position] = player

    drafted_player_id_set = set()
    with open(get_draft_class_drafted_players_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, drafted_player in enumerate(reader):
            player_data = drafted_player["Selection"].split(" ")
            player_name_arr = player_data[0:]
            if len(player_name_arr[-1]) == 1:
                player_name_arr = player_name_arr[0:-1]
            player_name = " ".join(player_name_arr).lower()
            player_position = drafted_player["Position"].lower()
            if (
                player_position == "sp"
                or player_position == "rp"
                or player_position == "cl"
            ):
                player_position = "p"
            player = players_by_name[player_name][player_position]
            drafted_player_id_set.add(player["id"])
    return drafted_player_id_set
