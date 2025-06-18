from modifiers.base_modifier import BaseModifier


def get_overall_attribute_modifier(ovr, potential):
    potential_diff = potential - ovr

    if ovr >= 45:
        if potential_diff == 0:
            return 1.01
        elif potential_diff <= 5:
            return 1.02
        elif potential_diff <= 10:
            return 1.03
        return 1.045
    elif ovr >= 40:
        if potential_diff == 0:
            return 1
        elif potential_diff <= 5:
            return 1.007
        elif potential_diff <= 10:
            return 1.015
        return 1.025
    elif ovr >= 35:
        if potential_diff <= 10:
            return 1
        return 1.01
    elif ovr >= 30:
        return 1 if potential_diff >= 10 else 0.98
    elif ovr >= 25:
        return 0.99 if potential_diff >= 10 else 0.92
    return 0.965 if potential_diff >= 10 else 0.92


def get_all_over_attribute_modifiers(attributes):
    if all(attr >= 45 for attr in attributes):
        return 1.04
    if all(attr >= 40 for attr in attributes):
        return 1.03
    if all(attr >= 35 for attr in attributes):
        return 1.015
    if all(attr >= 30 for attr in attributes):
        return 1.0
    if all(attr >= 25 for attr in attributes):
        return 0.99
    return 0.97


class DraftPitcherOverallModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        modifier *= get_overall_attribute_modifier(player.stuff_ovr, player.stuff)
        modifier *= get_overall_attribute_modifier(player.movement_ovr, player.movement)
        modifier *= get_overall_attribute_modifier(player.control_ovr, player.control)
        attrs = [player.stuff_ovr, player.movement_ovr, player.control_ovr]
        modifier *= get_all_over_attribute_modifiers(attrs)
        return modifier
