from attribute_models.attribute_model import AttributeModel


class CenterFieldAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "CF"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - CF data.csv"

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
            [8, [55, 60, 50]],  # barely useable
            [13, [55, 70, 60]],  # barely useable
            [21, [60, 45, 60]],  # below average
            [26, [60, 60, 65]],  # below average
            [36, [60, 75, 80]],  # below average
            [52, [65, 70, 65]],  # solid regular
            [55, [70, 45, 50]],  # solid regular
            [66, [70, 70, 60]],  # top 5 at position
            [75, [80, 40, 40]],  # gold glove
            [81, [75, 60, 55]],  # gold glove
            [84, [75, 70, 70]],  # gold glove
            [91, [80, 65, 70]],  # gold glove
            [100, [80, 80, 80]],  # best ever
            [70, [70, 70, 70]],  # lower bounds constant
            [0, [50, 70, 70]],  # lower bounds
            [27, [70, 25, 70]],  # lower bounds
            [24, [70, 70, 25]],  # lower bounds
        ]
