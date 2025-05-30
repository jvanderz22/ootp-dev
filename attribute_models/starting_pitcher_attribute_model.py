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
            [71, [50, 80, 80]],  # ace
            [67, [75, 50, 60]],  # ace-ish
            [65, [60, 60, 65]],  # solid #2
            [63, [55, 55, 75]],  # solid #2
            [55, [55, 55, 55]],  # mid rotation
            [52, [70, 50, 45]],  # mid rotation
            [50, [55, 75, 45]],  # mid rotation
            [46, [55, 45, 60]],  # #5 starter
            [46, [50, 50, 65]],  # #5 starter
            [45, [70, 45, 45]],  # #5 starter
            [41, [50, 50, 50]],  # spot starter
            [38, [55, 45, 50]],  # spot starter
            [36, [70, 50, 40]],  # spot starter
            [35, [50, 35, 60]],  # spot starter
            [31, [70, 50, 35]],  # maybe some value with TCR
            [30, [55, 45, 45]],  # maybe some value with TCR
            [29, [45, 50, 50]],  # maybe some value with TCR
            [17, [45, 45, 45]],  # maybe some value with TCR
            [6, [40, 40, 40]],  # maybe some value with TCR
            [0, [35, 35, 35]],  # no value
            [66, [65, 65, 65]],  # lower bounds baseline
            [13, [65, 25, 65]],  # lower bounds
            [13, [35, 65, 65]],  # lower bounds
            [11, [65, 65, 30]],  # lower bounds
            [0, [40, 40, 40]],  # lower bounds
        ]
