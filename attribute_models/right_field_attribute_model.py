from attribute_models.attribute_model import AttributeModel


class RightFieldAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "RF"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - RF data.csv"

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
            "Range": "of_range",
            "Arm": "of_arm",
            "Error": "of_error",
        }

    @property
    def test_data(self):
        return [
            [7, [60, 45, 50]],  # barely useable
            [10, [45, 45, 45]],  # barely useable
            [12, [40, 80, 55]],  # barely useable
            [19, [60, 40, 60]],  # below average
            [20, [50, 65, 60]],  # below average
            [21, [55, 65, 40]],  # below average
            [32, [60, 50, 55]],  # solid regular
            [36, [55, 65, 60]],  # solid regular
            [44, [60, 60, 55]],  # above average
            [53, [60, 80, 80]],  # top 5 at position
            [62, [65, 65, 65]],  # gold glove
            [68, [65, 75, 65]],  # gold glove
            [75, [80, 80, 80]],  # just play CF
            [43, [60, 60, 60]],  # lower bounds constant
            [0, [40, 60, 60]],  # lower bounds
            [0, [60, 40, 60]],  # lower bounds
            [0, [60, 60, 30]],  # lower bounds
        ]
