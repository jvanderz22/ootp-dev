import csv
import getopt
import sys
from typing import Dict, List
from draft_class_files import get_ranked_players_file
from get_game_players import get_game_players
from models.game_players import GamePlayer
from printers.org_player_printer import OrgPlayerPrinter
from rankers.get_ranker import get_ranker
from utils.rank_graditated_model import RankGradiatedModel

# somewhere between 58 and 60 should be the minimum score for org summary value
player_ranking_points_model = RankGradiatedModel(
    [0, 58, 62, 65, 68, 70, 72, 75, 80, 85, 90, 100, 110, 120],
    [0, 0, 2.2, 6, 9, 11, 14, 19, 32, 45, 61, 81, 92, 100],
)


class PlayerSummary:
    def __init__(self, player: GamePlayer, player_score: Dict[str, float]):
        self._player = player
        self._player_score = player_score

    @property
    def player(self) -> GamePlayer:
        return self._player

    @property
    def player_score(self) -> Dict[str, float]:
        return self._player_score


class OrgSummaryPrinter:
    def __init__(self):
        self.game_players = get_game_players()
        self.org_player_printer = OrgPlayerPrinter()
        ranker = get_ranker()
        print(f"Printing evals from ranker: {ranker.__class__.__name__}")
        with open(get_ranked_players_file(ranker), newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            self.ranked_players = [player for player in reader]

    def print(self):
        print_summary = True
        try:
            opts, _args = getopt.getopt(sys.argv[1:], "o:t:d")
        except getopt.GetoptError:
            print("Invalid Option!")
            sys.exit(2)

        org_in_detail = None
        per_system_count = 10
        detailed_mode = False
        for opt, arg in opts:
            if opt == "-o":
                print_summary = False
                org_in_detail = arg
            if opt == "-t":
                per_system_count = int(arg)
            if opt == "-d":
                detailed_mode = True

        org_summary = self.create_org_summaries()
        rating_counts = {org: {} for org in org_summary.keys()}
        for org in org_summary.keys():
            org_score = sum(
                [
                    player_ranking_points_model.rank(
                        float(p.player_score["model_score"])
                    )
                    for p in org_summary[org]
                ]
            )
            top_10_specs = [
                p
                for p in org_summary[org]
                if int(p.player_score["overall_ranking"]) < 10
            ]
            top_50_specs = [
                p
                for p in org_summary[org]
                if int(p.player_score["overall_ranking"]) < 50
            ]
            top_100_specs = [
                p
                for p in org_summary[org]
                if int(p.player_score["overall_ranking"]) < 100
            ]
            top_250_specs = [
                p
                for p in org_summary[org]
                if int(p.player_score["overall_ranking"]) < 250
            ]
            top_500_specs = [
                p
                for p in org_summary[org]
                if int(p.player_score["overall_ranking"]) < 500
            ]
            rating_counts[org] = {
                "org_score": org_score,
                "top_10": len(top_10_specs),
                "top_50": len(top_50_specs),
                "top_100": len(top_100_specs),
                "top_250": len(top_250_specs),
                "top_500": len(top_500_specs),
            }

        if print_summary:
            # for org in sorted(rating_counts.keys()):
            print("Top Orgs:")
            for index, org in enumerate(
                sorted(
                    rating_counts.keys(),
                    key=lambda item: rating_counts[item]["org_score"],
                    reverse=True,
                )
            ):
                print(
                    f"{index + 1}. {org} ({float(rating_counts[org]['org_score']):.2f})"
                )
            print("\n-------")

            for org in sorted(
                rating_counts.keys(),
                key=lambda item: rating_counts[item]["org_score"],
                reverse=True,
            ):
                print(org)
                self.print_rating_counts(rating_counts[org])
                self.print_player_summaries(org_summary[org], per_system_count)

                print("\n")
                print("-------")

        if org_in_detail is not None:
            org_rating_count = rating_counts.get(org_in_detail)
            if org_rating_count is None:
                print(f"Unable to find org: {org}")
                print(f"Possible options are: {rating_counts.keys()}")
                return

            print(f"{org_in_detail} Summary:\n")

            self.print_rating_counts(org_rating_count)

            if detailed_mode is False:
                self.print_player_summaries(
                    org_summary[org_in_detail], per_system_count
                )
            else:
                players_to_print = org_summary[org_in_detail][0:per_system_count]
                for i, player_summary in enumerate(players_to_print):
                    self.org_player_printer.print_player(
                        player_summary.player_score, i + 1, player_summary.player
                    )

    def create_org_summaries(self):
        players_by_org = {}
        for player_ranking in self.ranked_players:
            player = self.game_players.get_player(player_ranking["id"])
            if players_by_org.get(player.org) == None:
                players_by_org[player.org] = []
            players_by_org[player.org].append(PlayerSummary(player, player_ranking))
        for org in players_by_org.keys():
            players_by_org[org] = sorted(
                players_by_org[org],
                key=lambda player: float(player.player_score["model_score"]),
                reverse=True,
            )
        return players_by_org

    def print_rating_counts(self, rating_count):
        print(f"Overall score: {float(rating_count['org_score']):.2f}")
        print(f"Top 10: {rating_count['top_10']}")
        print(f"Top 50: {rating_count['top_50']}")
        print(f"Top 100: {rating_count['top_100']}")
        print(f"Top 500: {rating_count['top_500']}")

    def print_player_summaries(
        self, org_summary: List[PlayerSummary], player_count: int = 10
    ):
        print("\nTop Players:")
        for i, player in enumerate(org_summary[0:player_count]):
            print(
                f"{i+1}. {player.player.name} {player.player.position} #{int(player.player_score['overall_ranking']) + 1} ({player.player_score['model_score']}, {player.player.potential} Pot) {player.player.age}, {player.player.level}"
            )


if __name__ == "__main__":
    printer = OrgSummaryPrinter()
    printer.print()
