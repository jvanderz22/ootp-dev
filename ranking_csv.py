import csv
import getopt
import sys

from drafted_players import get_drafted_player_ids
from draft_class_files import (
    get_draft_class_eval_model_file,
    get_draft_class_ranked_players_file,
    get_draft_class_upload_players_file,
)


def read_players():
    players_by_id = {}
    ranked_players = []
    with open(get_draft_class_eval_model_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for player in reader:
            ranked_players.append(player)
            players_by_id[player["id"]] = player
    return [ranked_players, players_by_id]


preference_list_files = [
    # "./preference_lists/round_2_picks.csv",
    # "./preference_lists/round_3_picks.csv",
    # "./preference_lists/round_4_picks.csv",
    # "./preference_lists/round_5_picks.csv",
    # "./preference_lists/post_round_5_picks.csv",
    # Ignore this list for now
    # './preference_lists/post_tenth_round_picks.csv',
]

end_of_draft_pref_list = "./preference_lists/post_round_10_picks.csv"


def create_ranking_csv(modifiers=None):
    debug_overvalued = False
    debug_undervalued = False
    [model_ranked_players, model_players_by_id] = read_players()
    drafted_players_set = get_drafted_player_ids()
    ranked_players = []
    ranked_player_ids = set()

    for file in preference_list_files:
        with open(file, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            players_to_rank = []
            for player in reader:
                model_player = model_players_by_id[player["ID"]]
                if model_player["id"] not in ranked_player_ids:
                    ranked_player_ids.add(model_player["id"])
                    players_to_rank.append(model_player)

        sorted_players = sorted(
            players_to_rank, key=lambda player: int(player["ranking"])
        )
        ranked_players.extend(sorted_players)
    for player in model_ranked_players:
        if player["id"] not in ranked_player_ids:
            ranked_player_ids.add(player["id"])
            ranked_players.append(player)

        # Add players I'm interested in at the end of the draft
        if len(ranked_player_ids) == 320:
            with open(end_of_draft_pref_list, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                players_to_rank = []
                for player in reader:
                    model_player = model_players_by_id[player["ID"]]
                    if model_player["id"] not in ranked_player_ids:
                        players_to_rank.append(model_player)
                sorted_players = sorted(
                    players_to_rank, key=lambda player: int(player["ranking"])
                )
                for player in sorted_players:
                    if player["id"] not in ranked_player_ids:
                        ranked_player_ids.add(player["id"])
                        ranked_players.append(player)

    ranked_player_field_names = [
        "overall_ranking",
        "model_ranking",
        "ranking_difference",
        "id",
        "name",
        "position",
        "age",
        "model_score",
        "position_player_score",
        "fielding_score_component",
        "batting_score_component",
        "pitcher_score",
        "in_game_potential",
        "demand",
        "raw_overall_score",
        "raw_ranking",
    ]
    if modifiers is not None:
        for player in ranked_players:
            modifier = modifiers.get(player["position"])
            if modifier is not None and modifier != 1:
                player["overall_score"] = float(player["overall_score"]) * modifier

        players_by_score = sorted(
            ranked_players,
            key=lambda player: float(player["overall_score"]),
            reverse=True,
        )

        for i, player in enumerate(players_by_score):
            player["ranking"] = i + 1
        ranked_players = players_by_score

    with open(get_draft_class_ranked_players_file(), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=ranked_player_field_names)
        writer.writeheader()
        for i, player in enumerate(ranked_players):

            ranking_difference = i - int(player["ranking"])
            if debug_overvalued:
                if i > 5 and i < 100 and ranking_difference < -30:
                    print("\n\n\novervalued player", i, player["ranking"], player)
            if debug_undervalued:
                if (
                    i > 120
                    and i < 200
                    and ranking_difference > 30
                    and int(player["in_game_potential"]) >= 35
                ):
                    print("\n\n\nundervalued player", i, player["ranking"], player)
            row = {
                "overall_ranking": i,
                "model_ranking": player["ranking"],
                "ranking_difference": i - int(player["ranking"]),
                "id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "batting_score_component": player["batting_score_component"],
                "fielding_score_component": player["fielding_score_component"],
                "model_score": player["overall_score"],
                "demand": player["demand"],
                "in_game_potential": player["in_game_potential"],
                "age": player["age"],
                "pitcher_score": player["pitcher_score"],
                "position_player_score": player["position_player_score"],
                "raw_overall_score": player["raw_overall_score"],
                "raw_ranking": player["raw_ranking"],
            }

            writer.writerow(row)

    upload_field_names = ["id", "name", "position", "age", "model_score", "demand"]
    with open(get_draft_class_upload_players_file(), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=upload_field_names)
        num_ranked_players = 0
        for player in ranked_players:
            if player["id"] in drafted_players_set:
                continue
            num_ranked_players += 1
            if num_ranked_players > 500:
                break
            row = {
                "id": player["id"],
                "name": player["name"],
                "position": player["position"],
                "age": player["age"],
                "model_score": player["overall_score"],
                "demand": player["demand"],
            }
            writer.writerow(row)


if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "c:",
            ["C=", "1B=", "2B=", "SS=", "3B=", "OF=", "SP=", "RP="],
        )
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)

    catcher = 1
    first_base = 1
    second_base = 1
    third_base = 1
    shortstop = 1
    outfielder = 1
    starting_pitcher = 1
    relief_pitcher = 1
    for opt, arg in opts:
        if opt == "--C":
            catcher = float(arg)
        if opt == "--1B":
            first_base = float(arg)
        if opt == "--2B":
            second_base = float(arg)
        if opt == "--3B":
            third_base = float(arg)
        if opt == "--SS":
            shortstop = float(arg)
        if opt == "--OF":
            outfielder = float(arg)
        if opt == "--SP":
            starting_pitcher = float(arg)
        if opt == "--RP":
            relief_pitcher = float(arg)

    create_ranking_csv({"C": catcher, "1B": first_base})
