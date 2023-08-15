from attribute_models.attribute_model import AttributeModel


class StartingPitcherAttributeModel(AttributeModel):
    def __init__(self, type="potential"):
        super().__init__()
        self.type = type

    @property
    def model_type(self):
        return "SP"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - SP data.csv"

    @property
    def fields(self):
        return [
            "Stuff",
            "Movement",
            "Control",
        ]

    @property
    def fields_mapping(self):
        return (
            self.potential_fields_mapping
            if self.type == "potential"
            else self.overall_fields_mapping
        )

    @property
    def potential_fields_mapping(self):
        return {
            "Stuff": "stuff",
            "Movement": "movement",
            "Control": "control",
        }

    @property
    def overall_fields_mapping(self):
        return {
            "Stuff": "stuff_ovr",
            "Movement": "movement_ovr",
            "Control": "control_ovr",
        }
