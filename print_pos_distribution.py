import csv
import getopt
import sys

from draft_class_files import get_draft_class_ranked_players_file
from get_game_players import get_game_players
from drafted_players import get_drafted_player_ids


def print_top_distribution(rank_count):
    position_player_count = 0
    pitcher_count = 0
    with open(get_draft_class_ranked_players_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, player in enumerate(reader):
            if i >= rank_count:
                break
            position = player["position"]
            if position == "SP" or position == "RP" or position == "CP":
                pitcher_count += 1
            else:
                position_player_count += 1
    print(f"Top {rank_count} distribution:\n")
    print(f"Total pitchers: {pitcher_count}")
    print(f"Total position players: {position_player_count}")


if __name__ == "__main__":
    rank_count = 50
    try:
        opts, args = getopt.getopt(sys.argv[1:], "n:p:t:arm")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-t":
            rank_count = int(arg)

    print_top_distribution(rank_count)
