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
            [11, [30, 80]],  # above average
            [14, [80, 30]],  # above average
            [15, [50, 50]],  # above average
            [21, [60, 60]],  # gold glove
            [23, [70, 70]],  # gold glove
            [25, [80, 60]],  # gold glove
            [5, [30, 30]],  # minimal player
            [0, [25, 30]],  # lower bounds
            [0, [30, 25]],  # lower bounds
        ]
