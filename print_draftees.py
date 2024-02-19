import csv
import getopt
import sys

from constants import RANKED_PLAYERS_FILE_PATH
from get_game_players import get_game_players
from drafted_players import get_drafted_player_ids, get_drafted_players_info


def print_player(player):
    print("------")
    print(f"{player.potential} {player.name} {player.position} {player.id}")


if __name__ == "__main__":
    game_players = get_game_players()
    print_count = 50
    position = None
    print_raw = False
    org = None
    maximum_potential = 80
    try:
        opts, args = getopt.getopt(sys.argv[1:], "m:p:t:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-m":
            maximum_potential = int(arg)
        if opt == "-p":
            position = arg
        if opt == "-t":
            print_count = int(arg)
        if opt == "-o":
            org = arg

    drafted_players = get_drafted_player_ids()
    with open(RANKED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        printed_players = 0
        players = [game_players.get_player(player["id"]) for player in reader]
        players = sorted(players, key=lambda player: player.potential, reverse=True)
        for i, player in enumerate(players):
            is_drafted = False
            if printed_players >= print_count:
                break
            if player.id in drafted_players:
                if position is not None:
                    if position != player.position:
                        continue
                if player.potential > maximum_potential:
                    continue
                print_player(player)
