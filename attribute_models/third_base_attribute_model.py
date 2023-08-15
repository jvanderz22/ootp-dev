from attribute_models.attribute_model import AttributeModel


class ThirdBaseAttributeModel(AttributeModel):
    right_hand_only = True

    @property
    def model_type(self):
        return "3B"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - 3B data.csv"

    @property
    def fields(self):
        return [
            "Range",
            "Arm",
            "Error",
        ]

    @property
    def fields_mapping(self):
        return {
            "Range": "if_range",
            "Arm": "if_arm",
            "Error": "if_error",
        }

    @property
    def test_data(self):
        return [
            [10, [50, 40, 50]],  # barely useable
            [35, [50, 55, 70]],  # solid regular
            [35, [60, 50, 60]],  # solid regular
            [70, [70, 70, 70]],  # gold glove
            [70, [80, 50, 80]],  # gold glove
            [70, [80, 80, 60]],  # gold glove
            [5, [35, 45, 55]],
            [0, [70, 70, 25]],  # lower bounds
            [0, [30, 70, 70]],  # lower bounds
            [15, [80, 20, 80]],  # lower bounds
        ]
