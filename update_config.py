import getopt
import sys

from draft_class_files import _ctx


if __name__ == "__main__":
    ranker_override = None
    try:
        opts, args = getopt.getopt(sys.argv[1:], "r:")
    except getopt.GetoptError:
        print("Invalid Option!")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-r":
            ranker_override = arg
    if ranker_override is not None:
        _ctx().save_config({"ranking_method": ranker_override})
