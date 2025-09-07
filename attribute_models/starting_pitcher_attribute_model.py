from attribute_models.attribute_model import AttributeModel


class StartingPitcherAttributeModel(AttributeModel):
    separate_test_train = True

    def __init__(self, type="potential"):
        super().__init__()
        self.type = type

    @property
    def model_type(self):
        return "SP"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - SP data.csv"

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

    50: 88
    60: 80
    70: 73
    80: 66
    85: 61
    90: 56
    95: 53
    100: 50
    105: 45
    110: 41
    120: 34
    130: 21

    """

    @property
    def test_data(self):
        return [
            [100, [80, 80, 80]],  # best pitcher in world
            [97, [80, 70, 70]],  # better than any pitcher in the league
            [96, [70, 80, 75]],  # better than any pitcher in the league
            [86, [70, 70, 70]],  # best pitcher in the league
            [85, [80, 60, 60]],  # best pitcher in the league
            [84, [65, 75, 70]],  # best pitcher in the league
            [81, [75, 55, 65]],  # best pitcher in the league
            [81, [75, 65, 55]],  # best pitcher in the league

            #  baselines
            [100, [80, 80, 80]], # best pitcher in the world
            [86, [70, 70, 70]], # best pitcher in the league
            [80, [65, 65, 65]], # ace
            [72, [60, 60, 60]], # ace-ish
            [61, [55, 55, 55]], # solid #2/3
            [50, [50, 50, 50]], # average starter
            [30, [45, 45, 45]], # emergency replacement
            [9, [40, 40, 40]], # no value
            [0, [35, 35, 35]],

            # outlier stuff
            [88, [80, 60, 60]], # ace
            [72, [80, 50, 50]], # ace-ish
            [43, [80, 40, 40]], # spot-starter with upside
            [30, [80, 35, 35]], # emergency replacement


            # outlier stuff (bad)
            [60, [40, 80, 80]], # #2/3
            [5, [35, 50, 50]],
            [5, [30, 70, 70]],
            [5, [30, 80, 80]],
            [0, [30, 50, 80]],
            [0, [30, 80, 50]],

            # outlier movement
            [83, [60, 80, 60]], # ace
            [65, [50, 70, 50]], # ace-ish
            [31, [40, 80, 40]], # emergency replacement
            [16, [35, 80, 35]], # little value

            # outlier movement (bad)
            [66, [80, 40, 80]], # ace-ish
            [20, [50, 35, 50]],
            [2, [50, 30, 50]],
            [32, [80, 30, 50]], # emergency replacement
            [7, [60, 30, 60]], # emergency replacement
            [12, [80, 25, 50]], # emergency replacement

            # outlier control
            [82, [60, 60, 80]], # ace
            [57, [50, 50, 70]], # above-average
            [22, [40, 40, 80]], # little value
            [10, [35, 35, 80]], # no value

            # outlier control (bad)
            [73, [80, 80, 40]], # ace-ish
            [16, [50, 50, 35]],
            [2, [50, 50, 30]],
            [22, [80, 50, 30]], # emergency replacement
            [13, [60, 60, 30]], # emergency replacement
            [7, [80, 50, 25]], # emergency replacement
        ]

    def __print_test_results(self, model):
        print("80, 80, 80", self.run(80, 80, 80))
        print("80, 40, 40", self.run(80, 40, 40))
