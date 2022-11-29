import csv
import math

from constants import RANKED_PLAYERS_FILE_PATH


def print_player(player):
    print("-------")
    print(
        f'{int(player["overall_ranking"]) + 1}. {player["name"]} {player["position"]}, {player["age"]}'
    )
    print(f'Model score: {player["model_score"]}')
    print(f'Potential: {player["in_game_potential"]}')
    print(f'Demand: {player["demand"]}')
    position_player_score = float(player["position_player_score"])
    pitcher_score = float(player["pitcher_score"])
    if max(pitcher_score, position_player_score) / 2 < min(
        pitcher_score, position_player_score
    ):
        print(
            f"Position player score: {position_player_score}, Pitcher score: {pitcher_score}"
        )


if __name__ == "__main__":
    print_count = 50
    with open(RANKED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, player in enumerate(reader):
            if i > print_count:
                break
            print_player(player)
            print("")
