from modifiers.base_modifier import BaseModifier

scouting_accuracy_modifiers = {
    "Very High": 1,
    "High": 0.98,
    "Average": 0.94,
    "Low": 0.75,
    "Very Low": 0.3,
}


class ScoutingAccuracyModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        return scouting_accuracy_modifiers[player.scouting_accuracy]
