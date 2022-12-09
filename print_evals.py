import csv
import getopt
import sys

from constants import RANKED_PLAYERS_FILE_PATH
from get_game_players import get_game_players
from drafted_players import get_drafted_player_ids


def print_player(player, index, is_drafted, game_player, print_opts={}):
    print_raw = print_opts.get("print_raw", False)
    print_minimal = print_opts.get("print_minimal", False)
    print("---------------------------")
    print(
        f'{index}. {player["name"]} {player["position"]} {player["age"]}, {player["id"]}'
    )
    if not print_minimal:
        print(f"Bat Hand: {game_player.bat_hand}, Throw Hand: {game_player.throw_hand}")
    if is_drafted:
        print(f"DRAFTED!")

    print(
        f'Overall Ranking: {int(player["overall_ranking"]) + 1}, Model score: {player["model_score"]}, Potential: {player["in_game_potential"]}'
    )
    if print_raw:
        print(
            f'Raw (demand-excluded) score: {player["raw_overall_score"]}, Raw Ranking: {player["raw_ranking"]}'
        )
    position_player_score = float(player["position_player_score"])
    pitcher_score = float(player["pitcher_score"])
    is_batter = False
    is_pitcher = False
    if position_player_score > pitcher_score:
        is_batter = True
    else:
        is_pitcher = True
    if max(pitcher_score, position_player_score) / 2 < min(
        pitcher_score, position_player_score
    ):
        is_batter = True
        is_pitcher = True
        print(
            f"Two way player! Position player score: {position_player_score}, Pitcher score: {pitcher_score}"
        )

    if is_batter and not print_minimal:
        print(
            f"Batting component: {player['batting_score_component']}, Fielding score component: {player['fielding_score_component']}"
        )
        print(
            f"Contact: {game_player.contact}, Gap: {game_player.gap}, Power: {game_player.power}, Eye: {game_player.eye}, Avoid K: {game_player.avoid_k}"
        )
        print(
            f"Speed: {game_player.speed}, Steal: {game_player.steal}, Running Ability: {game_player.running_ability}"
        )
        if game_player.if_range >= 40 and game_player.throw_hand == "Right":
            print(
                f"IF Range: {game_player.if_range}, IF Error: {game_player.if_error}, IF Arm: {game_player.if_arm}, Turn DP: {game_player.turn_dp}"
            )
        if game_player.of_range >= 40:
            print(
                f"OF Range: {game_player.of_range}, OF Error: {game_player.of_error}, OF Arm: {game_player.of_arm}"
            )
        if game_player.c_ability >= 45:
            print(f"C Ability: {game_player.c_ability}, C Arm: {game_player.c_arm}")

    if is_pitcher and not print_minimal:
        print(
            f"Stuff: {game_player.stuff}, Movement: {game_player.movement}, Control: {game_player.control}, Stamina: {game_player.stamina}"
        )
        print(f"Pitches: ", end="")
        for pitch in game_player.get_pitches():
            print(f"{pitch.capitalize()}: {getattr(game_player, pitch)}", end=", ")
        print("")
    if not print_minimal:
        print(
            f"Durability: {game_player.injury_prone}, Work Ethic: {game_player.work_ethic}, Intelligence: {game_player.intelligence}"
        )
        print(f'Demand: {player["demand"]}')


if __name__ == "__main__":
    game_players = get_game_players()
    print_count = 50
    position = None
    show_drafted = False
    print_raw = False
    print_minimal = False
    player_name = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "n:p:t:arm")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-r":
            print_raw = True
        if opt == "-m":
            print_minimal = True
        if opt == "-a":
            show_drafted = True
        if opt == "-p":
            position = arg
        if opt == "-n":
            player_name = arg
        if opt == "-t":
            print_count = int(arg)

    drafted_players = get_drafted_player_ids()
    with open(RANKED_PLAYERS_FILE_PATH, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        printed_players = 0
        for i, player in enumerate(reader):
            is_drafted = False
            if printed_players >= print_count:
                break
            if player_name is not None:
                if player_name.lower() not in player["name"].lower():
                    continue
            if player["id"] in drafted_players:
                is_drafted = True
                if not show_drafted:
                    continue
            if position is not None:
                if position.lower() != player["position"].lower():
                    continue

            printed_players += 1
            print_player(
                player,
                printed_players,
                is_drafted,
                game_players.get_player(player["id"]),
                {"print_raw": print_raw, "print_minimal": print_minimal},
            )
            print("")
