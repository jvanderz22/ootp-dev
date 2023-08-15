from constants import DRAFT_CLASS_NAME


def get_draft_class_data_file():
    return f"datasets/{DRAFT_CLASS_NAME}.csv"


def get_draft_class_eval_model_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/eval_model.csv"


def get_draft_class_config_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/config.json"


def get_draft_class_ranked_players_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/ranked_players.csv"


def get_draft_class_upload_players_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/upload_ranked_players.csv"


def get_draft_class_drafted_players_file():
    return f"./processed_classes/{DRAFT_CLASS_NAME}/drafted_players.csv"
