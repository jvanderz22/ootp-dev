import csv

from draft_class_files import get_draft_class_data_file
from models.game_players import GamePlayers


def get_game_players(ctx=None):
    with open(get_draft_class_data_file(ctx), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        all_players = [player for player in reader]
    return GamePlayers(all_players)
