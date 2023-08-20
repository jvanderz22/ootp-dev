import os
from constants import DRAFT_CLASS_NAME


def get_draft_class_data_file():
    return f"datasets/{DRAFT_CLASS_NAME}.csv"


def get_ranker_folder(ranker):
    ranker_name = ranker.__class__.__name__
    folder_name = f"./processed_classes/{DRAFT_CLASS_NAME}/{ranker_name}"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name


def get_draft_class_eval_model_file(ranker):
    folder_name = get_ranker_folder(ranker)
    return f"{folder_name}/eval_model.csv"


def get_draft_class_config_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/config.json"


def get_ranked_players_file(ranker):
    folder_name = get_ranker_folder(ranker)
    return f"{folder_name}/ranked_players.csv"


def get_draft_class_upload_players_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/upload_ranked_players.csv"


def get_draft_class_drafted_players_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/drafted_players.csv"
