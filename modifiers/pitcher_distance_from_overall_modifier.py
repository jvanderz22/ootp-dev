from modifiers.base_modifier import BaseModifier
from scoring.pitcher_scorer import PitcherScorer


# .91 ^ 3 = .75
modifier1 = 0.91
# .92 ^ 3 = .77
modifier2 = 0.92
# .93^3 = .8
modifier3 = 0.93
# .94^3 = .83
modifier4 = 0.94
# .95^3 = .85
modifier5 = 0.95
# .958^3 = .88
modifier6 = 0.958
# .973^3 = .92
modifier7 = 0.973
# .987^3 = .96
modifier8 = 0.987
# .993^3 = .98
modifier9 = 0.995


def modifier_for_attr(overall_attr, potential_attr):
    diff = potential_attr - overall_attr
    if diff == 0:
        return 1
    if overall_attr <= 20:
        if diff >= 40:
            return modifier1
        if diff >= 30:
            return modifier2
        elif diff >= 20:
            return modifier3
        elif diff >= 10:
            return modifier5
        else:
            return modifier7
    if overall_attr <= 25:
        if diff >= 40:
            return modifier2
        if diff >= 30:
            return modifier3
        elif diff >= 10:
            return modifier7
        else:
            return modifier8
    if overall_attr <= 35:
        if diff >= 40:
            return modifier4
        if diff >= 30:
            return modifier6
        elif diff >= 20:
            return modifier7
        elif diff >= 10:
            return modifier8
        else:
            return modifier9
    if overall_attr <= 45:
        if diff >= 30:
            return modifier5
        if diff >= 20:
            return modifier6
        elif diff >= 10:
            return modifier8
        else:
            return modifier9
    if diff >= 40:
        return modifier5
    if diff >= 30:
        return modifier7
    elif diff >= 20:
        return modifier8
    else:
        return modifier9


class PitcherDistanceFromOverallModifier(BaseModifier):
    overall_scorer = PitcherScorer("overall")
    potential_scorer = PitcherScorer()

    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        modifier *= modifier_for_attr(player.stuff_ovr, player.stuff)
        modifier *= modifier_for_attr(player.movement_ovr, player.movement)
        modifier *= modifier_for_attr(player.control_ovr, player.control)
        return modifier
