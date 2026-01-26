from attribute_models.relief_pitcher_attribute_model import ReliefPitcherAttributeModel
from attribute_models.starting_pitcher_attribute_model import (
    StartingPitcherAttributeModel,
)

from regressed_models.base_regression_model import BaseRegressionModel


class PitchingRegressionModel(BaseRegressionModel):
    # Pitching attributes to blend between overall and potential
    ATTRIBUTES = [
        ("stuff", "stuff_ovr"),
        ("movement", "movement_ovr"),
        ("control", "control_ovr"),
    ]

    SCENARIO_PROBABILITIES = [0.4, 0.4, 0.4]
    is_pitching_model = True

    def __init__(self, type: str):
        if type == "SP":
            self.model = StartingPitcherAttributeModel("overall")
        if type == "RP":
            self.model = ReliefPitcherAttributeModel("overall")
