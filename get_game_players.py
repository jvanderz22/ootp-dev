import csv

from models.game_players import GamePlayers
from constants import DATASET_FILE_PATH


def get_game_players():
    with open(DATASET_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        all_players = [player for player in reader]
    game_players = GamePlayers(all_players)
    return game_players
