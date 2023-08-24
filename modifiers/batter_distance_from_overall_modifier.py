from modifiers.base_modifier import BaseModifier
from scoring.position_player_scorer import PositionPlayerScorer


# .9^4 = .65
modifier1 = 0.89
# .937^4 = .77
modifier2 = 0.91
# .931^4 = .75
modifier3 = 0.925
# .937^4 = .77
modifier4 = 0.937
# .946^4 = .8
modifier5 = 0.946
# .955^4 = .83
modifier6 = 0.955
# .961^4 = .85
modifier7 = 0.961
# .97^4 = .88
modifier8 = 0.97
# .98^4 = .922
modifier9 = 0.98
# .99 ^ 4 = .96
modifier10 = 0.99
# .995 ^ 4 = .98
modifier11 = 0.995


def modifier_for_attr(overall_attr, potential_attr):
    diff = potential_attr - overall_attr
    if diff == 0:
        return 1
    if overall_attr <= 20:
        if diff >= 50:
            return modifier1
        if diff >= 40:
            return modifier2
        if diff >= 30:
            return modifier3
        elif diff >= 20:
            return modifier4
        elif diff >= 10:
            return modifier6
        else:
            return modifier9
    if overall_attr <= 25:
        if diff >= 60:
            return modifier1
        if diff >= 50:
            return modifier2
        if diff >= 40:
            return modifier3
        if diff >= 30:
            return modifier4
        elif diff >= 20:
            return modifier5
        elif diff >= 10:
            return modifier8
        else:
            return modifier10
    if overall_attr <= 35:
        if diff >= 50:
            return modifier2
        if diff >= 40:
            return modifier3
        if diff >= 30:
            return modifier5
        elif diff >= 20:
            return modifier7
        elif diff >= 10:
            return modifier8
        else:
            return modifier10
    if overall_attr <= 45:
        if diff >= 40:
            return modifier5
        if diff >= 30:
            return modifier7
        if diff >= 20:
            return modifier8
        elif diff >= 10:
            return modifier10
        else:
            return modifier11
    if diff >= 30:
        return modifier4
    elif diff >= 25:
        return modifier5
    elif diff >= 15:
        return modifier8
    elif diff >= 10:
        return modifier9
    else:
        return modifier11


class BatterDistanceFromOverallModifier(BaseModifier):
    overall_scorer = PositionPlayerScorer("overall")
    potential_scorer = PositionPlayerScorer()

    @classmethod
    def calculate_player_modifier(cls, player):
        modifier = 1
        modifier *= modifier_for_attr(player.contact_ovr, player.contact)
        modifier *= modifier_for_attr(player.power_ovr, player.power)
        modifier *= modifier_for_attr(player.eye_ovr, player.eye)
        modifier *= modifier_for_attr(player.avoid_k_ovr, player.avoid_k)
        return 1
