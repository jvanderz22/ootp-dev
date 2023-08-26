import getopt
import json
import sys

from draft_class_files import get_draft_class_config_file


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
        with open(get_draft_class_config_file(), "r") as jsonfile:
            class_config = json.load(jsonfile)
        class_config["ranking_method"] = ranker_override
        with open(get_draft_class_config_file(), "w") as f:
            json.dump(class_config, f)
