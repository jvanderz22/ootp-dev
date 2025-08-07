import getopt
import json
import sys
from get_game_players import get_game_players


class OrgPlayerPrinter:
    def __init__(self):
        self.game_players = get_game_players()

    def get_args(self):
        print_count = 10
        position = None
        player_name = None
        org = None
        max_potential = None
        max_age = None
        verbose = False
        try:
            opts, args = getopt.getopt(sys.argv[1:], "n:p:t:o:m:a:v")
        except getopt.GetoptError:
            print("Invalid Option!")
            sys.exit(2)
        for opt, arg in opts:
            if opt == "-p":
                position = arg
            if opt == "-n":
                player_name = arg
            if opt == "-t":
                print_count = int(arg)
            if opt == "-o":
                org = arg
            if opt == "-a":
                max_age = int(arg)
            if opt == "-m":
                max_potential = int(arg)
            if opt == "-v":
                verbose = True
        return {
            "print_count": print_count,
            "position": position,
            "player_name": player_name,
            "max_age": max_age,
            "max_potential": max_potential,
            "org": org,
            "verbose": verbose,
        }

    def print(self, players):
        opts = self.get_args()
        print_count = opts.get("print_count", 50)
        player_name = opts.get("player_name")
        print_minimal = opts.get("print_minimal", False)
        sort_by_potential = opts.get("sort_by_potential", False)
        position = opts.get("position")
        org = opts.get("org")
        verbose = opts.get("verbose", False)
        printed_players = 0

        if sort_by_potential:
            players = sorted(
                players, key=lambda player: player["in_game_potential"], reverse=True
            )

        for i, player in enumerate(players):
            if printed_players >= print_count:
                break
            if player_name is not None:
                if player_name.lower() not in player["name"].lower():
                    continue
            if org is not None:
                if (
                    self.game_players.get_player(player["id"]).org.lower()
                    != org.lower()
                ):
                    continue
            if position is not None:
                if position.lower() == "pos":
                    search_pos = ["c", "1b", "2b", "3b", "ss", "rf", "cf", "lf", "dh"]
                elif position.lower() == "pit":
                    search_pos = ["sp", "rp", "cl"]
                elif position.lower() == "of":
                    search_pos = ["rf", "cf", "lf"]
                elif position.lower() == "rp":
                    search_pos = ["rp", "cl"]
                else:
                    search_pos = [position.lower()]
                if player["position"].lower() not in search_pos:
                    continue

            printed_players += 1
            self.print_player(
                player,
                printed_players,
                self.game_players.get_player(player["id"]),
                {"print_minimal": print_minimal, "verbose": verbose},
            )

    def print_player(self, player, index, game_player, print_opts={}):
        print_minimal = print_opts.get("print_minimal", False)
        print_verbose = print_opts.get("verbose", False)
        print("---------------------------")
        print(
            f"{index}. {game_player.name} {game_player.position} {game_player.age}, {game_player.org} ({game_player.level}) {game_player.id}"
        )
        if not print_minimal:
            print(
                f"Bat Hand: {game_player.bat_hand}, Throw Hand: {game_player.throw_hand}"
            )

        print(
            f'Overall Ranking: {int(player["overall_ranking"]) + 1}, Model score: {player["model_score"]}, Potential: {player["in_game_potential"]}'
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
                f"Contact: {game_player.contact} ({game_player.contact_ovr}), Gap: {game_player.gap} ({game_player.gap_ovr}), Power: {game_player.power} ({game_player.power_ovr}), Eye: {game_player.eye} ({game_player.eye_ovr}), Avoid K: {game_player.avoid_k} ({game_player.avoid_k_ovr})"
            )
            print(
                f"Speed: {game_player.speed}, Steal: {game_player.steal}, Running Ability: {game_player.running_ability}"
            )
            if game_player.if_range >= 40 and game_player.throw_hand == "Right":
                print(
                    f"IF Range: {game_player.if_range}, IF Error: {game_player.if_error}, IF Arm: {game_player.if_arm}, Turn DP: {game_player.turn_dp}"
                )
            elif game_player.if_range >= 30:
                print(
                    f"1B ONLY! IF Range: {game_player.if_range}, IF Error: {game_player.if_error}, IF Arm: {game_player.if_arm}, Turn DP: {game_player.turn_dp}"
                )
            if game_player.of_range >= 40:
                print(
                    f"OF Range: {game_player.of_range}, OF Error: {game_player.of_error}, OF Arm: {game_player.of_arm}"
                )
            if game_player.c_framing >= 45:
                print(
                    f"C Framing: {game_player.c_framing}, C Blocking: {game_player.c_blocking} C Arm: {game_player.c_arm}"
                )

        if is_pitcher and not print_minimal:
            print(
                f"Stuff: {game_player.stuff} ({game_player.stuff_ovr}), Movement: {game_player.movement} ({game_player.movement_ovr}), Control: {game_player.control} ({game_player.control_ovr}), Stamina: {game_player.stamina}"
            )
            print(f"Pitches: ", end="")
            for pitch in game_player.get_pitches():
                print(f"{pitch.capitalize()}: {getattr(game_player, pitch)}", end=", ")
            print("")
            print(f"FB Velocity: {game_player.velocity}")
        if not print_minimal:
            print(
                f"Durability: {game_player.injury_prone}, Work Ethic: {game_player.work_ethic}, Intelligence: {game_player.intelligence}, Leadership: {game_player.leadership}"
            )

        if print_verbose and player["components"] is not None:
            components = json.loads(player["components"].replace("'", '"'))
            print("\nPlayer Components:", end="")

            def is_pitcher_modifier(k):
                return "Pitcher" in k

            def is_pos_modifier(k):
                return "Pos" in k

            keys = components.keys()
            filtered_keys = []
            for key in keys:
                if is_pitcher_modifier(key) and not is_pitcher:
                    continue
                if is_pos_modifier(key) and not is_batter:
                    continue
                filtered_keys.append(key)
            key_chunks = [
                filtered_keys[x : x + 2] for x in range(0, len(filtered_keys), 2)
            ]

            for keys in key_chunks:
                print("\n  ", end="")
                for i, key in enumerate(keys):
                    val_str = f"{key}: {components[key]}"
                    extra_spaces = 0 if i > 0 else 60 - len(val_str)
                    print(f"{val_str}{' ' * extra_spaces}", end=" ")

        print("")
