import getopt
import json
import sys
from drafted_players import get_drafted_player_ids, get_drafted_players_info
from get_game_players import get_game_players


class DraftProspectPrinter:
    def __init__(self):
        self.drafted_players = get_drafted_player_ids()
        self.drafted_player_info = get_drafted_players_info()
        self.game_players = get_game_players()

    def get_args(self):
        print_count = 10
        position = None
        show_drafted = False
        sort_by_potential = False
        show_drafted_only = False
        drafted_round = None
        print_minimal = False
        drafted_org = None
        player_name = None
        verbose = False
        try:
            opts, args = getopt.getopt(sys.argv[1:], "n:p:t:r:o:amsdv")
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
            if opt == "-o":
                drafted_org = arg
            if opt == "-v":
                verbose = True

        return {
            "print_count": print_count,
            "player_name": player_name,
            "show_drafted": show_drafted,
            "show_drafted_only": show_drafted_only,
            "drafted_round": drafted_round,
            "print_minimal": print_minimal,
            "position": position,
            "sort_by_potential": sort_by_potential,
            "drafted_org": drafted_org,
            "verbose": verbose,
        }

    def print(self, players):
        opts = self.get_args()
        print_count = opts.get("print_count", 50)
        player_name = opts.get("player_name")
        show_drafted = opts.get("show_drafted", False)
        show_drafted_only = opts.get("show_drafted_only", False)
        drafted_round = opts.get("drafted_round")
        drafted_org = opts.get("drafted_org")
        print_minimal = opts.get("print_minimal", False)
        sort_by_potential = opts.get("sort_by_potential", False)
        position = opts.get("position")
        verbose = opts.get("verbose", False)
        printed_players = 0

        if sort_by_potential:
            players = sorted(
                players, key=lambda player: player["in_game_potential"], reverse=True
            )

        for i, player in enumerate(players):
            player_draft_info = self.drafted_player_info.get(player["id"])
            is_drafted = False
            if printed_players >= print_count:
                break
            if player_name is not None:
                if player_name.lower() not in player["name"].lower():
                    continue
            if player["id"] in self.drafted_players:
                is_drafted = True
                if (
                    drafted_org is not None
                    and drafted_org.lower() != player_draft_info.get("team", "").lower()
                ):
                    continue
                elif not show_drafted and not show_drafted_only and drafted_org is None:
                    continue
                elif (
                    drafted_round is not None
                    and player_draft_info["round"] != drafted_round
                ):
                    continue
            else:
                if show_drafted_only or drafted_org is not None:
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
                player_draft_info,
                self.game_players.get_player(player["id"]),
                {"print_minimal": print_minimal, "verbose": verbose},
            )
            print("")

    def print_player(self, player, index, draft_info, game_player, print_opts={}):
        print_minimal = print_opts.get("print_minimal", False)
        print_verbose = print_opts.get("verbose", False)
        print("---------------------------")
        print(
            f'{index}. {player["name"]} {player["position"]} {player["age"]}, {player["id"]}'
        )
        if not print_minimal:
            print(
                f"Bat Hand: {game_player.bat_hand}, Throw Hand: {game_player.throw_hand}"
            )
        if draft_info:
            print(
                f"Drafted by {draft_info['team']} in round {draft_info['round']} at pick {draft_info['round_selection']} (#{draft_info['overall_selection']} overall)"
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
                f"Contact: {game_player.contact}, Gap: {game_player.gap}, Power: {game_player.power}, Eye: {game_player.eye}, Avoid K: {game_player.avoid_k}"
            )
            print(
                f"Speed: {game_player.speed}, Steal: {game_player.steal}, Running Ability: {game_player.running_ability}"
            )
            print(
                f"Contact Ovr: {game_player.contact_ovr}, Gap Ovr: {game_player.gap_ovr}, Power Ovr: {game_player.power_ovr}, Eye Ovr: {game_player.eye_ovr}, Avoid K: {game_player.avoid_k_ovr}"
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
                f"Stuff: {game_player.stuff}, Movement: {game_player.movement}, Control: {game_player.control}, Stamina: {game_player.stamina}"
            )
            print(
                f"Stuff Ovr: {game_player.stuff_ovr}, Movement Ovr: {game_player.movement_ovr}, Control Ovr: {game_player.control_ovr}"
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
            print(f'Demand: {player["demand"]}')

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
