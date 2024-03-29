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

    # need to score down for ratings below individual skill thresholds faster
    # big drops at:
    #   40 contact
    #   50 power (without good contact skills)
    #   40 power (regardless of contact skills)
    #   30 power (regardless of contact skills)
    #   40 eye
    #   40/35 avoid k (40 can carry other elite skills, 35 really hurts regardless)
    @property
    def test_data(self):
        return [
            [100, [80, 80, 80, 80, 80]],  # balanced archetype
            [93, [70, 70, 70, 70, 70]],  # balanced archetype - 180 WRC+
            [82, [65, 65, 65, 65, 65]],  # balanced archetype - 160 WRC+
            [65, [60, 60, 60, 60, 60]],  # balanced archetype - 130 WRC+
            [59, [60, 60, 60, 55, 55]],  # balanced archetype - 120 WRC+
            [58, [65, 50, 55, 65, 55]],  # balanced archetype - 120 WRC+
            [56, [65, 35, 60, 55, 55]],  # balanced archetype - low gap - 110 WRC+
            [54, [65, 55, 60, 55, 35]],  # balanced archetype - low avoid K - 110 WRC+
            [52, [65, 55, 60, 35, 55]],  # balanced archetype - low eye - 110 WRC+
            [51, [55, 55, 55, 55, 55]],  # balanced archetype - 100 WRC+
            [38, [50, 50, 50, 50, 50]],  # balanced archetype - 90 WRC+
            [22, [45, 45, 45, 45, 45]],  # balanced archetype - 75 WRC+
            [11, [40, 40, 40, 40, 40]],  # balanced archetype - 55 WRC+
            [2, [35, 35, 35, 35, 35]],  # balanced archetype - 30 WRC+
            [95, [65, 70, 80, 70, 55]],  # power archetype - 180 WRC+
            [82, [55, 60, 75, 70, 50]],  # power archetype - 160 WRC+
            [73, [50, 55, 70, 65, 45]],  # power archetype - 140 WRC+
            [65, [45, 55, 70, 60, 45]],  # power archetype - 125 WRC+
            [62, [45, 65, 70, 55, 40]],  # power archetype - 120 WRC+
            [57, [45, 40, 65, 50, 45]],  # power archetype - 110 WRC+
            [51, [45, 40, 65, 50, 45]],  # power archetype - 110 WRC+
            [47, [45, 45, 70, 45, 35]],  # power archetype - 100 WRC+
            [46, [40, 65, 70, 50, 35]],  # power archetype - 95 WRC+
            [44, [40, 45, 70, 50, 35]],  # power archetype - 90 WRC+
            [40, [45, 45, 70, 45, 30]],  # power archetype - 90 WRC+
            [31, [45, 40, 70, 35, 35]],  # power archetype - 80 WRC+
            [26, [45, 35, 65, 45, 40]],  # power archetype - 80 WRC+
            [24, [40, 50, 60, 45, 45]],  # power archetype - 80 WRC+
            [10, [40, 40, 70, 40, 30]],  # power archetype - 55 WRC+
            [3, [30, 35, 65, 30, 30]],  # power archetype - 30 WRC+
            [93, [80, 80, 60, 80, 80]],  # contact archetype - 180 WRC+
            [78, [80, 80, 40, 80, 80]],  # contact archetype - 150 WRC+
            [76, [70, 70, 50, 75, 70]],  # contact archetype - 150 WRC+
            [62, [75, 80, 35, 65, 75]],  # contact archetype - 130 WRC+
            [58, [70, 75, 40, 55, 65]],  # contact archetype - 120 WRC+
            [54, [75, 70, 40, 40, 80]],  # contact archetype - 110 WRC+
            [54, [65, 60, 45, 60, 60]],  # contact archetype - 110 WRC+
            [49, [65, 60, 30, 60, 65]],  # contact archetype - 100 WRC+
            [44, [80, 60, 25, 25, 80]],  # contact archetype - 95 WRC+
            [28, [60, 60, 30, 30, 60]],  # contact archetype - 80 WRC+
            [17, [50, 45, 30, 45, 50]],  # contact archetype - 65 WRC+
            [2, [45, 40, 20, 40, 45]],  # contact archetype - 30 WRC+
            # sd samples
            # pache
            [51, [55, 60, 50, 50, 50]],
            # perez
            [49, [50, 50, 45, 50, 55]],
            # Ledesma
            [68, [45, 55, 70, 65, 45]],
            # Ramos
            [53, [65, 60, 35, 55, 65]],
            # Hiramo
            [25, [50, 50, 25, 50, 65]],
            # Karros
            [27, [45, 55, 60, 55, 40]],
            # Vukovich
            [17, [40, 55, 55, 50, 30]],
            # Soderstrom
            [51, [50, 60, 55, 50, 45]],
            # Medina
            [24, [55, 55, 35, 25, 70]],
        ]
