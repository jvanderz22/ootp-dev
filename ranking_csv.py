import csv


def read_players():
    players_by_id = {}
    ranked_players = []
    with open("./processed_data/eval_model.csv", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for player in reader:
            ranked_players.append(player)
            players_by_id[player["id"]] = player
    return [ranked_players, players_by_id]


preference_list_files = [
    "./preference_lists/round_2_picks.csv",
    "./preference_lists/round_3_picks.csv",
    "./preference_lists/round_4_picks.csv",
    "./preference_lists/round_5_picks.csv",
    "./preference_lists/post_round_5_picks.csv",
    # Ignore this list for now
    # './preference_lists/post_tenth_round_picks.csv',
]

end_of_draft_pref_list = "./preference_lists/post_round_10_picks.csv"
drafted_players = "./preference_lists/drafted_players.csv"
stats_plus_drafted_players = (
    "./preference_lists/OOTP Prospect Lists - Drafted Players.csv"
)


def get_drafted_player_ids():
    players_by_name = {}
    with open("./processed_data/eval_model.csv", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for player in reader:
            name = player["name"].lower()
            players_by_name[name] = player

    drafted_player_id_set = set()
    with open(stats_plus_drafted_players, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for i, drafted_player in enumerate(reader):
            player_data = drafted_player["Player"]
            player_name_arr = player_data.split(" ")[1:]
            if len(player_name_arr[-1]) == 1:
                player_name_arr = player_name_arr[0:-1]
            player_name = " ".join(player_name_arr).lower()
            player = players_by_name[player_name]
            drafted_player_id_set.add(player["id"])
    return drafted_player_id_set


def create_ranking_csv():
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
        "pitcher_score",
        "in_game_potential",
        "demand",
    ]
    with open("./processed_data/ranked_players.csv", "w", newline="") as csvfile:
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
                "model_score": player["overall_score"],
                "demand": player["demand"],
                "in_game_potential": player["in_game_potential"],
                "age": player["age"],
                "pitcher_score": player["pitcher_score"],
                "position_player_score": player["position_player_score"],
            }

            writer.writerow(row)

    upload_field_names = ["id", "name", "position", "age", "model_score", "demand"]
    with open("./processed_data/upload_ranked_players.csv", "w", newline="") as csvfile:
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
    create_ranking_csv()
