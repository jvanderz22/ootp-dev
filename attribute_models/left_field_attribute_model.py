from attribute_models.attribute_model import AttributeModel


class LeftFieldAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "LF"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - LF data.csv"

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
            [5, [40, 55, 50]],  # barely useable
            [9, [45, 45, 45]],  # barely useable
            [16, [50, 50, 60]],  # below average
            [17, [50, 60, 40]],  # below average
            [19, [55, 65, 40]],  # below average
            [26, [55, 65, 55]],  # solid regular
            [28, [55, 45, 70]],  # solid regular
            [34, [60, 40, 60]],  # above average
            [36, [60, 60, 55]],  # above average
            [45, [80, 35, 60]],  # gold glove
            [47, [65, 65, 65]],  # gold glove
            [51, [70, 55, 65]],  # gold glove
            [55, [80, 80, 80]],  # just play CF
            [39, [60, 60, 60]],  # lower bounds constant
            [4, [35, 60, 60]],  # lower bounds
            [5, [60, 25, 60]],  # lower bounds
            [7, [60, 60, 30]],  # lower bounds
        ]
