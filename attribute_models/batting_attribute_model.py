from attribute_models.attribute_model import AttributeModel


class BattingAttributeModel(AttributeModel):
    def __init__(self, type="potential"):
        super().__init__()
        self.type = type

    @property
    def model_type(self):
        return "batting"

    @property
    def file_path(self):
        return "./training_data/OOTP Models - Batter data.csv"

    @property
    def fields(self):
        return ["Contact", "Gap", "Power", "Eye", "K"]

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
            "Contact": "contact",
            "Gap": "gap",
            "Power": "power",
            "Eye": "eye",
            "K": "avoid_k",
        }

    @property
    def overall_fields_mapping(self):
        return {
            "Contact": "contact_ovr",
            "Gap": "gap_ovr",
            "Power": "power_ovr",
            "Eye": "eye_ovr",
            "K": "avoid_k_ovr",
        }
