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
