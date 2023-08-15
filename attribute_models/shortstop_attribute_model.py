from attribute_models.attribute_model import AttributeModel


class ShortstopAttributeModel(AttributeModel):
    right_hand_only = True

    @property
    def model_type(self):
        return "SS"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - SS data.csv"

    @property
    def fields(self):
        return [
            "Range",
            "Arm",
            "Error",
            "Dp",
        ]

    @property
    def fields_mapping(self):
        return {
            "Range": "if_range",
            "Arm": "if_arm",
            "Error": "if_error",
            "Dp": "turn_dp",
        }

    @property
    def test_data(self):
        return [
            [17, [55, 65, 65, 65]],  # barely useable
            [22, [60, 60, 60, 55]],  # barely useable
            [48, [65, 65, 65, 65]],  # solid regular
            [56, [70, 50, 50, 55]],  # solid regular
            [65, [70, 65, 70, 65]],  # top 5 at position
            [85, [75, 75, 65, 70]],  # gold glove
            [90, [80, 60, 55, 60]],  # gold glove
            [100, [80, 80, 80, 80]],  # best ever
            [45, [65, 60, 65, 60]],  # lower bounds baseline
            [0, [65, 30, 60, 65]],  # lower bounds
            [0, [65, 60, 30, 60]],  # lower bounds
            [0, [45, 60, 65, 60]],  # lower bounds
            [0, [65, 60, 65, 30]],  # lower bounds
        ]
