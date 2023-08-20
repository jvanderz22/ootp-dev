from attribute_models.attribute_model import AttributeModel


class FirstBaseAttributeModel(AttributeModel):
    @property
    def model_type(self):
        return "1B"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - 1B data.csv"

    @property
    def fields(self):
        return [
            "Range",
            "Error",
        ]

    @property
    def fields_mapping(self):
        return {
            "Range": "if_range",
            "Error": "if_error",
        }

    @property
    def test_data(self):
        return [
            [4, [50, 50]],  # barely useable
            [7, [40, 65]],  # barely useable
            [16, [45, 65]],  # below average
            [19, [50, 60]],  # below average
            [27, [50, 70]],  # solid regular
            [29, [60, 60]],  # solid regular
            [40, [55, 75]],  # above average
            [43, [60, 70]],  # above average
            [25, [70, 70]],  # gold glove
            [25, [80, 60]],  # gold glove
            [25, [60, 60]],  # gold glove
            [5, [30, 30]],  # minimal player
            [0, [25, 30]],  # lower bounds
            [0, [30, 25]],  # lower bounds
        ]
