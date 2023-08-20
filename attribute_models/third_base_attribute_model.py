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

    # need to drop these guys off faster
    @property
    def test_data(self):
        return [
            [4, [50, 40, 50]],  # barely useable
            [7, [40, 50, 65]],  # barely useable
            [16, [45, 55, 65]],  # below average
            [19, [50, 55, 60]],  # below average
            [27, [50, 55, 70]],  # solid regular
            [29, [60, 50, 60]],  # solid regular
            [40, [55, 70, 75]],  # above average
            [43, [60, 55, 70]],  # above average
            [59, [70, 70, 70]],  # gold glove
            [66, [80, 80, 60]],  # gold glove
            [70, [80, 50, 80]],  # gold glove
            [57, [65, 80, 80]],  # range upper bounds (less than SS)
            [63, [70, 80, 80]],  # range upper bounds
            [5, [35, 45, 55]],
            [0, [70, 70, 25]],  # lower bounds
            [0, [30, 70, 70]],  # lower bounds
            [4, [70, 30, 70]],  # lower bounds
        ]
