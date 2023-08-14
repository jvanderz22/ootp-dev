from attribute_models.attribute_model import AttributeModel
from models.game_players import PLAYER_FIELDS


class RunningAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "running"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - Running data.csv"

    @property
    def fields(self):
        return [
            "Speed",
            "Steal",
            "Baserunning",
        ]

    @property
    def fields_mapping(self):
        return {
            "Speed": "speed",
            "Steal": "steal",
            "Baserunning": "running_ability",
        }
