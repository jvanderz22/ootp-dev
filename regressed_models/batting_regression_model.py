from attribute_models.batting_attribute_model import BattingAttributeModel
from models.game_players import PLAYER_FIELDS, GamePlayer


class BattingRegressionModel:
    # Blend percentages for scenario generation (0% to 100% of potential improvement)
    BLEND_PERCENTAGES = [0.75, 0.9, 1.0]

    # Batting attributes to blend between overall and potential
    BATTING_ATTRIBUTES = [
        ("contact", "contact_ovr"),
        ("gap", "gap_ovr"),
        ("power", "power_ovr"),
        ("eye", "eye_ovr"),
        ("avoid_k", "avoid_k_ovr"),
    ]

    def __init__(self):
        self.batting_model = BattingAttributeModel("overall")

    def _exponential_interpolation(
        self, overall_value: float, potential_value: float, blend_percentage: float
    ) -> float:
        """
        Use exponential interpolation between overall and potential based on OVR level.

        Low-OVR players (20-40) develop slowly and asymptotically approach potential.
        High-OVR players (60+) can develop more linearly or faster.

        This creates realistic development curves where a 20 OVR player reaching 25 OVR
        is valued differently than a 70 OVR player reaching 75 OVR.

        Args:
            overall_value: Current overall rating (20-80 scale)
            potential_value: Potential rating (20-80 scale)
            blend_percentage: How far along development (0.0 to 1.0)

        Returns:
            Interpolated value using exponential curve
        """
        if blend_percentage <= 0:
            return overall_value
        if blend_percentage >= 1.0:
            return potential_value

        # Normalize overall to 0-1 range (20-80 scale)
        overall_percentile = (overall_value - 20) / 60.0

        # Use aggressive exponential scaling for low-OVR players that tapers off by 40 OVR
        if overall_percentile < 0.333:  # 20-40 OVR range
            # Linear taper from 20 OVR) to 40 OVR
            exponent = 1.8 - (overall_percentile / 0.333) * 1.2
            adjusted_blend = blend_percentage**exponent
        else:
            # 40+ OVR: linear development
            adjusted_blend = blend_percentage

        # Interpolate using adjusted blend
        gap = potential_value - overall_value
        return overall_value + (adjusted_blend * gap)

    def _create_player_scenario(
        self, player: GamePlayer, blend_percentage: float
    ) -> GamePlayer:
        """
        Create a deep copy of the player with batting attributes blended
        between current overall and potential values.

        blend_percentage: 0.0 = keep current overall, 1.0 = reach full potential

        Returns:
            GamePlayer: Deep copy with blended attribute values
        """
        new_attrs = {}

        blended_values = []
        for potential_attr, overall_attr in self.BATTING_ATTRIBUTES:
            potential_value = getattr(player, potential_attr)
            overall_value = getattr(player, overall_attr)

            # Use exponential interpolation based on overall OVR level
            blended_value = self._exponential_interpolation(
                overall_value, potential_value, blend_percentage
            )

            # Round to nearest 5 to smooth out discontinuities in model
            blended_value = round(blended_value / 5) * 5
            blended_values.append(blended_value)

            # Set the blended value on the copy's underlying dict
            # This ensures the batting model sees the blended attributes
            csv_attr_name = PLAYER_FIELDS[overall_attr]
            new_attrs[csv_attr_name] = str(int(blended_value))

        return player.create_copy(new_attrs)

    def run(self, player: GamePlayer) -> float:
        """
        Run batting model with scenarios for potential outcomes
        based on percentage of full potential reached.

        Returns:
            float: Weighted composite batting score that captures underlying potential
            and likelihood of reaching full the potential.
        """
        weighted_scores = []
        scenario_probabilities = []

        for blend_percentage in self.BLEND_PERCENTAGES:
            # Create player copy with blended attributes
            scenario_player = self._create_player_scenario(player, blend_percentage)

            # Run batting model on this scenario
            scenario_score = self.batting_model.run(scenario_player)

            # just weight all scenarios equally
            scenario_probability = 1

            # Weight and accumulate
            weighted_scores.append(scenario_score * scenario_probability)
            scenario_probabilities.append(scenario_probability)

        # Calculate weighted scenario composite as a weighted average
        total_probability = sum(scenario_probabilities)
        weighted_scenario_score = (
            sum(weighted_scores) / total_probability if total_probability > 0 else 0
        )

        return weighted_scenario_score
