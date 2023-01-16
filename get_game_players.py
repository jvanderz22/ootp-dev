import csv

from models.game_players import GamePlayers
from draft_class_files import get_draft_class_data_file


def get_game_players():
    with open(get_draft_class_data_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        all_players = [player for player in reader]
    game_players = GamePlayers(all_players)
    return game_players
