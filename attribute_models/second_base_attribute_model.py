from attribute_models.attribute_model import AttributeModel


class SecondBaseAttributeModel(AttributeModel):
    right_hand_only = True

    @property
    def model_type(self):
        return "2B"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - 2B data.csv"

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
            [11, [50, 65, 60, 55]],  # barely useable
            [13, [55, 45, 40, 45]],  # barely useable
            [14, [55, 50, 40, 55]],  # barely useable
            [38, [65, 45, 65, 50]],  # solid regular
            [42, [60, 50, 60, 65]],  # solid regular
            [61, [70, 65, 70, 65]],  # top 5 at position
            [65, [75, 45, 45, 75]],  # gold glove
            [70, [80, 30, 80, 80]],  # gold glove
            [75, [80, 60, 80, 80]],  # gold glove
            [80, [80, 80, 80, 80]],  # just play SS
            [32, [55, 55, 55, 55]],  # lower bounds baseline
            [0, [40, 55, 55, 55]],  # lower bounds
            [4, [55, 25, 55, 55]],  # lower bounds
            [0, [55, 55, 25, 55]],  # lower bounds
            [3, [55, 55, 55, 25]],  # lower bounds
        ]
