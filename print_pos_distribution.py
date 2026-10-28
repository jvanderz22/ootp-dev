import getopt
import sys

from ranking_csv import ranked_csv_rows
from rankers.get_ranker import get_ranker


def print_top_distribution(rank_count):
    position_player_count = 0
    pitcher_count = 0
    rp_count = 0
    get_ranker()  # prints the class's ranking method
    for i, player in enumerate(ranked_csv_rows() or []):
        if i >= rank_count:
            break
        position = player["position"]
        if position == "SP":
            pitcher_count += 1
        elif position == "RP" or position == "CL":
            pitcher_count += 1
            rp_count += 1
        else:
            position_player_count += 1
    print(f"Top {rank_count} distribution:\n")
    print(f"Total pitchers: {pitcher_count} ({rp_count} relievers)")
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
