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
