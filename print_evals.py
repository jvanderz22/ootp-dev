import csv
import getopt
import json
import sys

from draft_class_files import (
    get_draft_class_config_file,
    get_ranked_players_file,
)
from printers.draft_prospect_printer import DraftProspectPrinter
from printers.org_player_printer import OrgPlayerPrinter


def get_printer():
    print_method = None
    with open(get_draft_class_config_file(), "r") as jsonfile:
        json_data = json.load(jsonfile)
        print_method = json_data.get("print_method", "draft_prospects")
    if print_method == "draft_prospects":
        return DraftProspectPrinter()
    elif print_method == "org_players":
        return OrgPlayerPrinter()
    raise ValueError("Invalid Printer")


if __name__ == "__main__":
    with open(get_ranked_players_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        printed_players = 0
        players = [player for player in reader]

        printer = get_printer()
        printer.print(players)
