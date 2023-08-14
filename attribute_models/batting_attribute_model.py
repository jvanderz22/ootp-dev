from attribute_models.attribute_model import AttributeModel
from models.game_players import PLAYER_FIELDS


class BattingAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "batting"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - Batter data.csv"

    @property
    def fields(self):
        return ["Contact", "Gap", "Power", "Eye", "K"]

    @property
    def fields_mapping(self):
        return {
            "Contact": "contact",
            "Gap": "gap",
            "Power": "power",
            "Eye": "eye",
            "K": "avoid_k",
        }
