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
    is_batter = False
    if position_player_score > pitcher_score:
        is_batter = True
    if max(pitcher_score, position_player_score) / 2 < min(
        pitcher_score, position_player_score
    ):
        is_batter = True
        print(
            f"Position player score: {position_player_score}, Pitcher score: {pitcher_score}"
        )

    if is_batter:
        print(
            f"Batting component: {player['batting_score_component']}, Fielding score component: {player['fielding_score_component']}"
        )

    print(f'ID: {player["id"]}')


if __name__ == "__main__":
    print_count = 50
    with open(RANKED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, player in enumerate(reader):
            if i > print_count:
                break
            print_player(player)
            print("")
