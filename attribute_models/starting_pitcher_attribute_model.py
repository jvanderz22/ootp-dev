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
            [90, [80, 60, 70]],  # best pitcher in league
            [88, [70, 75, 70]],  # best pitcher in league
            [79, [70, 55, 75]],  # ace
            [77, [75, 55, 65]],  # ace
            [75, [65, 75, 70]],  # ace
            [67, [75, 50, 60]],  # ace-ish
            [62, [60, 60, 65]],  # solid #2
            [60, [55, 55, 75]],  # solid #2
            [50, [55, 55, 55]],  # mid rotation
            [47, [70, 50, 45]],  # mid rotation
            [46, [55, 75, 45]],  # mid rotation
            [40, [55, 45, 60]],  # #5 starter
            [40, [50, 50, 65]],  # #5 starter
            [38, [70, 45, 45]],  # #5 starter
            [32, [50, 50, 50]],  # spot starter
            [29, [55, 45, 50]],  # spot starter
            [27, [70, 50, 40]],  # spot starter
            [24, [50, 35, 60]],  # spot starter
            [22, [70, 50, 35]],  # maybe some value with TCR
            [20, [45, 50, 55]],  # maybe some value with TCR
            [10, [45, 45, 45]],  # maybe some value with TCR
            [66, [65, 65, 65]],  # lower bounds baseline
            [13, [65, 30, 65]],  # lower bounds
            [10, [40, 65, 65]],  # lower bounds
            [8, [65, 65, 30]],  # lower bounds
        ]
