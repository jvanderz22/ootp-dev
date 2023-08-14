from modifiers.base_modifier import BaseModifier


def get_overall_attribute_modifier(attribute):
    if attribute >= 45:
        return 1.14
    elif attribute >= 40:
        return 1.08
    elif attribute >= 35:
        return 1.035
    elif attribute >= 30:
        return 1
    elif attribute >= 25:
        return 0.985
    return 0.95


class PitcherOverallModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        modifier *= get_overall_attribute_modifier(player.stuff_ovr)
        modifier *= get_overall_attribute_modifier(player.movement_ovr)
        modifier *= get_overall_attribute_modifier(player.control_ovr)
        return modifier
