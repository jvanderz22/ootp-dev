from attribute_models.batting_attribute_model import BattingAttributeModel
from regressed_models.base_regression_model import BaseRegressionModel


class BattingRegressionModel(BaseRegressionModel):

    # Batting attributes to blend between overall and potential
    ATTRIBUTES = [
        ("contact", "contact_ovr"),
        ("gap", "gap_ovr"),
        ("power", "power_ovr"),
        ("eye", "eye_ovr"),
        ("avoid_k", "avoid_k_ovr"),
    ]

    def __init__(self):
        self.model = BattingAttributeModel("overall")
