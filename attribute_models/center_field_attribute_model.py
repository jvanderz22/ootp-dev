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
