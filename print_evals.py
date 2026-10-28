import getopt
import sys

from draft_class_files import _ctx
from printers.draft_prospect_printer import DraftProspectPrinter
from printers.org_player_printer import OrgPlayerPrinter
from ranking_csv import ranked_csv_rows
from rankers.get_ranker import get_ranker


def get_printer():
    print_method = _ctx().load_config().get("print_method") or "draft_prospects"
    if print_method == "draft_prospects":
        return DraftProspectPrinter()
    elif print_method == "org_players":
        return OrgPlayerPrinter()
    raise ValueError("Invalid Printer")


if __name__ == "__main__":
    ranker = get_ranker()
    print(f"Printing evals from ranker: {ranker.__class__.__name__}")
    players = ranked_csv_rows(with_breakdown=True) or []
    printer = get_printer()
    printer.print(players)
