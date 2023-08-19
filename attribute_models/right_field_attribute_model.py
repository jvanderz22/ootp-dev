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
            [6, [45, 45, 45]],  # barely useable
            [9, [40, 80, 55]],  # barely useable
            [14, [60, 30, 60]],  # below average
            [17, [50, 65, 60]],  # below average
            [19, [55, 65, 40]],  # below average
            [27, [60, 50, 55]],  # solid regular
            [30, [55, 65, 60]],  # solid regular
            [34, [60, 60, 55]],  # above average
            [43, [60, 80, 80]],  # top 5 at position
            [45, [65, 65, 65]],  # gold glove
            [50, [65, 75, 65]],  # gold glove
            [75, [80, 80, 80]],  # just play CF
            [33, [60, 60, 60]],  # lower bounds constant
            [0, [40, 60, 60]],  # lower bounds
            [0, [60, 40, 60]],  # lower bounds
            [0, [60, 60, 30]],  # lower bounds
        ]
