from attribute_models.attribute_model import AttributeModel
from models.game_players import PLAYER_FIELDS


class ReliefPitcherAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "RP"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - RP data.csv"

    @property
    def fields(self):
        return [
            "Stuff",
            "Movement",
            "Control",
        ]

    @property
    def fields_mapping(self):
        return {
            "Stuff": "stuff",
            "Movement": "movement",
            "Control": "control",
        }