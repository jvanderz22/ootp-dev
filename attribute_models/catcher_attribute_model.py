from attribute_models.attribute_model import AttributeModel


class CatcherAttributeModel(AttributeModel):
    right_hand_only = True

    @property
    def model_type(self):
        return "C"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - C data.csv"

    @property
    def fields(self):
        return ["C Ability", "C Arm"]

    @property
    def fields_mapping(self):
        return {"C Arm": "c_arm", "C Ability": "c_ability"}
