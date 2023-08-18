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
    print_count = 50
    position = None
    show_drafted = False
    sort_by_potential = False
    show_drafted_only = False
    drafted_round = None
    print_minimal = False
    player_name = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "n:p:t:r:amsd")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-m":
            print_minimal = True
        if opt == "-a":
            show_drafted = True
        if opt == "-p":
            position = arg
        if opt == "-n":
            player_name = arg
        if opt == "-d":
            show_drafted_only = True
        if opt == "-r":
            drafted_round = arg
        if opt == "-t":
            print_count = int(arg)
        if opt == "-s":
            sort_by_potential = True

    with open(get_ranked_players_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        printed_players = 0
        players = [player for player in reader]

        if sort_by_potential:
            players = sorted(
                players, key=lambda player: player["in_game_potential"], reverse=True
            )
        printer = get_printer()
        printer.print(
            players,
            {
                "print_count": print_count,
                "player_name": player_name,
                "show_drafted": show_drafted,
                "show_drafted_only": show_drafted_only,
                "drafted_round": drafted_round,
                "print_minimal": print_minimal,
                "position": position,
            },
        )
