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

    @property
    def test_data(self):
        return [
            [18, [40, 65]],  # barely useable
            [26, [65, 30]],  # barely useable
            [43, [50, 70]],  # solid regular
            [47, [55, 70]],  # solid regular
            [49, [65, 35]],  # solid regular
            [51, [60, 55]],  # solid regular
            [61, [65, 60]],  # top 5 at position
            [80, [70, 55]],  # gold glove
            [85, [75, 60]],  # gold glove
            [100, [75, 75]],  # best ever
            [0, [35, 45]],  # lower bound
            [0, [30, 65]],  # lower bound
            [0, [55, 30]],  # lower bound
        ]
