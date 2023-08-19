import getopt
import sys
from get_game_players import get_game_players


class OrgPlayerPrinter:
    def __init__(self):
        self.game_players = get_game_players()

    def print(self, player_scores, opts={}):
        print_count = opts.get("print_count", 50)
        player_name = opts.get("player_name")
        position = opts.get("position")
        printed_players = 0
        for i, player_score in enumerate(player_scores):
            player = self.game_players.get_player(player_score["id"])
            if printed_players >= print_count:
                break
            if player_name is not None:
                if player_name.lower() not in player.name.lower():
                    continue
            if position is not None:
                if position.lower() == "pos":
                    search_pos = ["c", "1b", "2b", "3b", "ss", "rf", "cf", "lf", "dh"]
                elif position.lower() == "pit":
                    search_pos = ["sp", "rp", "cl"]
                elif position.lower() == "of":
                    search_pos = ["rf", "cf", "lf"]
                else:
                    search_pos = [position.lower()]
                if player.position.lower() not in search_pos:
                    continue

            printed_players += 1
            self.print_player(player, player_score, printed_players)
            print("")

    def print_player(self, player, player_score, index):
        print("---------------------------")
        print("")
        print(f"{index}. {player.name} {player.position} {player.age}, {player.id}")
        print(f"Bat Hand: {player.bat_hand}, Throw Hand: {player.throw_hand}")

        print(
            f'Overall Ranking: {int(player_score["overall_ranking"]) + 1}, Model score: {player_score["model_score"]}, Potential: {player_score["in_game_potential"]}'
        )
        position_player_score = float(player_score["position_player_score"])
        pitcher_score = float(player_score["pitcher_score"])
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

        if is_batter:
            print("")
            print(
                f"Batting component: {player_score['batting_score_component']}, Fielding score component: {player_score['fielding_score_component']}"
            )
            print(f"Contact Ovr: {player.contact_ovr}, Contact Pot: {player.contact}")
            print(f"Gap Ovr: {player.gap_ovr}, Gap Pot: {player.gap}")
            print(f"Power Ovr: {player.power_ovr}, Power Pot: {player.power}")
            print(f"Eye Ovr: {player.eye_ovr}, Eye Pot: {player.eye}")
            print(f"Avoid K: {player.avoid_k_ovr}, Avoid K Pot: {player.avoid_k}")
            print(
                f"Speed: {player.speed}, Steal: {player.steal}, Running Ability: {player.running_ability}"
            )
            if player.if_range >= 40 and player.throw_hand == "Right":
                print(
                    f"IF Range: {player.if_range}, IF Error: {player.if_error}, IF Arm: {player.if_arm}, Turn DP: {player.turn_dp}"
                )
            elif player.if_range >= 30:
                print(
                    f"1B Ratings Only. IF Range: {player.if_range}, IF Error: {player.if_error}, IF Arm: {player.if_arm}, Turn DP: {player.turn_dp}"
                )
            if player.of_range >= 40:
                print(
                    f"OF Range: {player.of_range}, OF Error: {player.of_error}, OF Arm: {player.of_arm}"
                )
            if player.c_ability >= 45:
                print(f"C Ability: {player.c_ability}, C Arm: {player.c_arm}")
            print("")

        if is_pitcher:
            print("")
            print(f"Stuff Ovr: {player.stuff_ovr}, Stuff Pot: {player.stuff}")
            print(
                f"Movement Ovr: {player.movement_ovr}, Movement Pot: {player.movement}"
            )
            print(f"Control Ovr: {player.control_ovr}, Control Pot: {player.control}")
            print(f"Stamina: {player.stamina}")
            print(f"Pitches: ", end="")
            for pitch in player.get_pitches():
                print(f"{pitch.capitalize()}: {getattr(player, pitch)}", end=", ")
        print("")
        print(
            f"Durability: {player.injury_prone}, Work Ethic: {player.work_ethic}, Intelligence: {player.intelligence}, Leadership: {player.leadership}"
        )
