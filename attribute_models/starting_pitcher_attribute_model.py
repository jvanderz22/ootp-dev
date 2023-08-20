from attribute_models.attribute_model import AttributeModel


class StartingPitcherAttributeModel(AttributeModel):
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

    @property
    def test_data(self):
        return [
            [100, [80, 80, 80]],  # best pitcher in world
            [90, [80, 70, 70]],  # best pitcher in league
            [86, [70, 75, 70]],  # best pitcher in league
            [75, [70, 55, 75]],  # ace
            [72, [75, 55, 65]],  # ace
            [71, [65, 75, 70]],  # ace
            [65, [75, 50, 60]],  # ace-ish
            [59, [60, 60, 65]],  # solid #2
            [57, [55, 55, 75]],  # solid #2
            [51, [55, 55, 55]],  # mid rotation
            [47, [70, 50, 45]],  # mid rotation
            [45, [55, 75, 45]],  # mid rotation
            [43, [55, 45, 60]],  # #5 starter
            [43, [50, 50, 65]],  # #5 starter
            [41, [70, 45, 45]],  # #5 starter
            [35, [50, 50, 50]],  # spot starter
            [32, [55, 45, 50]],  # spot starter
            [32, [70, 50, 40]],  # spot starter
            [27, [50, 35, 60]],  # spot starter
            [25, [70, 50, 35]],  # maybe some value with TCR
            [24, [45, 50, 55]],  # maybe some value with TCR
            [15, [45, 45, 45]],  # maybe some value with TCR
            [66, [65, 65, 65]],  # lower bounds baseline
            [13, [65, 25, 65]],  # lower bounds
            [13, [35, 65, 65]],  # lower bounds
            [11, [65, 65, 30]],  # lower bounds
            [0, [40, 40, 40]],  # lower bounds
        ]
