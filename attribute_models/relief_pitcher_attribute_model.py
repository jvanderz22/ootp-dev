from attribute_models.attribute_model import AttributeModel
from models.game_players import PLAYER_FIELDS


class ReliefPitcherAttributeModel(AttributeModel):
    def __init__(self, type="potential"):
        super().__init__()
        self.type = type

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
        return (
            self.potential_fields_mapping
            if self.type == "potential"
            else self.overall_fields_mapping
        )

    @property
    def potential_fields_mapping(self):
        return {
            "Stuff": "stuff",
            "Movement": "movement",
            "Control": "control",
        }

    @property
    def overall_fields_mapping(self):
        return {
            "Stuff": "stuff_ovr",
            "Movement": "movement_ovr",
            "Control": "control_ovr",
        }

    @property
    def test_data(self):
        return [
            [100, [80, 80, 80]],  # best reliever pitcher in world
            [98, [80, 70, 70]],  # best reliever pitcher in world
            [86, [80, 50, 60]],  # elite backend reliever
            [83, [75, 60, 60]],  # elite backend reliever
            [68, [75, 45, 70]],  # solid backend reliever
            [63, [70, 55, 60]],  # solid backend reliever
            [54, [75, 45, 45]],  # middle-reliever
            [51, [60, 55, 60]],  # middle-reliever
            [47, [70, 35, 50]],  # middle-reliever
            [45, [50, 55, 75]],  # control-first middle-reliever
            [37, [50, 55, 55]],  # swingman
            [33, [65, 55, 45]],  # swingman
            [21, [60, 50, 45]],  # fringy reliever
            [19, [50, 45, 50]],  # fringy reliever
            [17, [80, 30, 30]],  # fringy reliever
            [16, [45, 55, 60]],  # fringy reliever
            [11, [55, 55, 40]],  # fringy reliever
            [95, [75, 75, 75]],  # lower bounds baseline
            [15, [75, 25, 75]],  # lower bounds
            [7, [40, 75, 75]],  # lower bounds
            [11, [75, 75, 25]],  # lower bounds
        ]
