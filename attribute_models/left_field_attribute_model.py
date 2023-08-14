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
