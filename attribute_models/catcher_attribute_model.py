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
        return ["C Blocking", "C Framing", "C Arm"]

    @property
    def fields_mapping(self):
        return {"C Arm": "c_arm", "C Blocking": "c_blocking", "C Framing": "c_framing"}

    @property
    def test_data(self):
        return [
            [11, [50, 40, 65]],  # barely useable
            [20, [40, 50, 65]],  # barely useable
            [26, [50, 65, 30]],  # barely useable
            [43, [55, 50, 70]],  # solid regular
            [47, [55, 55, 70]],  # solid regular
            [49, [50, 65, 35]],  # solid regular
            [51, [55, 60, 55]],  # solid regular
            [55, [70, 50, 70]],  # solid regular
            [61, [60, 65, 60]],  # top 5 at position
            [76, [50, 75, 50]],  # solid regular
            [80, [70, 70, 55]],  # gold glove
            [85, [65, 75, 60]],  # gold glove
            [100, [75, 75, 75]],  # best ever
            [10, [65, 65, 25]],  # lower bound
            [0, [35, 35, 70]],  # lower bound
            [0, [65, 30, 30]],  # lower bound
            [0, [35, 65, 30]],  # lower bound
        ]
