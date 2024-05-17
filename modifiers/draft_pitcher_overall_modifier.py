from modifiers.base_modifier import BaseModifier


def get_overall_attribute_modifier(attribute):
    if attribute >= 45:
        return 1.045
    elif attribute >= 40:
        return 1.025
    elif attribute >= 35:
        return 1.01
    elif attribute >= 30:
        return 1
    elif attribute >= 25:
        return 0.99
    return 0.98


def get_all_over_attribute_modifiers(attributes):
    if all(attr >= 45 for attr in attributes):
        return 1.1
    if all(attr >= 40 for attr in attributes):
        return 1.07
    if all(attr >= 35 for attr in attributes):
        return 1.04
    if all(attr >= 30 for attr in attributes):
        return 1.01
    if all(attr >= 25 for attr in attributes):
        return 0.985
    return 0.97


class DraftPitcherOverallModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        modifier *= get_overall_attribute_modifier(player.stuff_ovr)
        modifier *= get_overall_attribute_modifier(player.movement_ovr)
        modifier *= get_overall_attribute_modifier(player.control_ovr)
        attrs = [player.stuff_ovr, player.movement_ovr, player.control_ovr]
        modifier *= get_all_over_attribute_modifiers(attrs)
        return modifier
