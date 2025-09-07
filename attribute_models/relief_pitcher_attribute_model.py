from attribute_models.attribute_model import AttributeModel
from models.game_players import PLAYER_FIELDS


class ReliefPitcherAttributeModel(AttributeModel):
    separate_test_train = True

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

    """
    Rough FIP- prediction to model score guide:

    50: 70
    70: 62
    80: 55
    90: 50 - baseline for solid setup man
    95: 45
    100: 40 -- baseline for 50/50/50
    105: 35
    110: 27
    120: 12
    130: 0

    """

    @property
    def test_data(self):
        return [
            # baselines
            [80, [80, 80, 80]],
            [65, [70, 70, 70]],
            [53, [60, 60, 60]],
            [37, [50, 50, 50]],
            [16, [45, 45, 45]],
            [0, [40, 40, 40]],


            #outlier stuff
            [68, [80, 55, 55]], # elite closer
            [33, [80, 40, 40]], # untrustworthy
            [10, [80, 30, 30]], # little value

            [56, [65, 55, 55]], # solid closer

            #outlier stuff (bad)
            [63, [55, 80, 80]],
            [45, [45, 70, 70]],
            [37, [45, 60, 60]],
            [26, [45, 55, 55]],
            [27, [40, 70, 70]],
            [17, [35, 70, 70]],

            #outlier movement
            [68, [55, 80, 55]],
            [33, [40, 80, 40]],
            [16, [30, 80, 30]],

            #outlier movement (bad)
            [73, [80, 55, 80]],
            [66, [70, 45, 70]],
            [50, [60, 55, 60]],
            [45, [70, 40, 70]],
            [39, [55, 45, 55]],
            [31, [60, 40, 60]],
            [20, [70, 30, 70]],
            [5, [70, 25, 70]],

            #outlier control
            [61, [55, 55, 80]],
            [16, [40, 40, 80]],
            [2, [30, 30, 80]],

            #outlier control (bad)
            [73, [80, 80, 55]],
            [53, [70, 70, 45]],
            [50, [60, 60, 55]],
            [38, [55, 55, 45]],
            [48, [70, 70, 40]],
            [18, [70, 70, 30]],
            [5, [70, 70, 25]],

        ]
