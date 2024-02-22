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
            [85, [80, 80, 80]],  # best reliever pitcher ever
            [80, [80, 70, 70]],  # best reliever pitcher in league
            [71, [80, 50, 60]],  # elite backend reliever
            [67, [75, 60, 60]],  # elite backend reliever
            [55, [75, 45, 70]],  # solid backend reliever
            [53, [70, 55, 60]],  # solid backend reliever
            [46, [60, 55, 60]],  # middle-reliever
            [44, [75, 45, 45]],  # middle-reliever
            [39, [70, 35, 50]],  # middle-reliever
            [38, [50, 55, 75]],  # control-first middle-reliever
            [36, [55, 55, 55]],  # borderline middle-reliever
            [33, [65, 55, 45]],  # swingman
            [30, [55, 50, 55]],  # swingman
            [27, [50, 55, 55]],  # swingman
            [20, [60, 50, 45]],  # fringy reliever
            [16, [50, 45, 50]],  # fringy reliever
            [14, [80, 30, 30]],  # fringy reliever
            [13, [45, 55, 60]],  # fringy reliever
            [12, [50, 50, 50]],  # fringy reliever
            [9, [55, 55, 40]],  # fringy reliever
            [78, [75, 75, 75]],  # lower bounds baseline
            [12, [75, 25, 75]],  # lower bounds
            [6, [40, 75, 75]],  # lower bounds
            [3, [45, 45, 45]],  # lower bound
            [10, [75, 75, 25]],  # lower bounds
        ]
