from modifiers.base_modifier import BaseModifier


def get_overall_attribute_modifier(attribute):
    if attribute >= 45:
        return 1.055
    elif attribute >= 40:
        return 1.025
    elif attribute >= 35:
        return 1
    elif attribute >= 30:
        return 0.99
    elif attribute >= 25:
        return 0.98
    return 0.96


class DraftBatterOverallModifier(BaseModifier):
    @classmethod
    def calculate_player_modifier(cls, player, _model_score):
        modifier = 1
        modifier *= get_overall_attribute_modifier(player.contact_ovr)
        modifier *= get_overall_attribute_modifier(player.power_ovr)
        modifier *= get_overall_attribute_modifier(player.eye_ovr)
        modifier *= get_overall_attribute_modifier(player.avoid_k_ovr)
        return modifier
