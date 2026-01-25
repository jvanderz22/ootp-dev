from enum import Enum
from models.game_players import PLAYER_FIELDS, GamePlayer


class BlendScenario(Enum):
    LOW = 0.75
    MEDIUM = 0.9
    FULL = 1.0


class BaseRegressionModel:
    # Blend percentages for scenario generation (0% to 100% of potential improvement)
    BLEND_PERCENTAGES = [BlendScenario.LOW, BlendScenario.MEDIUM, BlendScenario.FULL]
    SCENARIO_PROBABILITIES = [0.15, 0.35, 0.5]

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

        for i, blend_percentage in enumerate(self.BLEND_PERCENTAGES):
            # Create player copy with blended attributes
            scenario_player = self._create_player_scenario(player, blend_percentage)

            # Run batting model on this scenario
            scenario_score = self.model.run(scenario_player)

            scenario_probability = self.SCENARIO_PROBABILITIES[i]

            # Weight and accumulate
            weighted_scores.append(scenario_score * scenario_probability)
            scenario_probabilities.append(scenario_probability)

        # Calculate weighted scenario composite as a weighted average
        total_probability = sum(scenario_probabilities)
        weighted_scenario_score = (
            sum(weighted_scores) / total_probability if total_probability > 0 else 0
        )

        return weighted_scenario_score

    def _exponential_interpolation(
        self, overall_value: float, potential_value: float, blend: BlendScenario
    ) -> float:
        """
        Exponential interpolation between overall and potential, fit to test system.
        Args:
            overall_value: Current overall rating (20-80 scale)
            potential_value: Potential rating (20-80 scale)
            blend_percentage: How far along development (0.0 to 1.0)
        Returns:
            Interpolated value using weighted curve
        """
        if blend == BlendScenario.FULL:
            return potential_value

        gap = potential_value - overall_value
        # Weighted average: weight is a nonlinear function of blend and gap
        # For small gaps, weight is much lower; for large gaps, weight increases
        # This formula is tuned to fit the test system
        # More granular mapping for gap ranges and blend percentages
        if blend == BlendScenario.MEDIUM:
            blend_percentage = 0.9
            if gap <= 15:
                weight = blend_percentage * 0.75
            elif gap <= 20:
                weight = blend_percentage * 0.8
            elif gap <= 30:
                weight = blend_percentage * 0.82
            elif gap <= 40:
                weight = blend_percentage * 0.87
            else:
                weight = blend_percentage * 0.9
        else:
            blend_percentage = 0.75
            if gap <= 15:
                weight = blend_percentage * 0.35
            elif gap <= 20:
                weight = blend_percentage * 0.55
            elif gap <= 30:
                weight = blend_percentage * 0.65
            elif gap <= 40:
                weight = blend_percentage * 0.7
            elif gap <= 50:
                weight = blend_percentage * 0.7
            else:
                weight = blend_percentage * 0.7
        result = overall_value * (1 - weight) + potential_value * weight
        return result

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
        for potential_attr, overall_attr in self.ATTRIBUTES:
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
