from modifiers.base_rank_modifier import BaseRankModifier

age_modifiers = {17: 1.1, 18: 1.07, 19: 1.02, 20: 1, 21: 1, 22: 0.97, 23: 0.93}


class DraftAgeModifier(BaseRankModifier):
    @classmethod
    def calculate_player_modifier(cls, player, rank):
        modifier_weight = 1
        age_modifier = age_modifiers.get(player.age, 0.9)

        max_weight_rank = 150
        min_weight_rank = 50

        if rank < min_weight_rank:
            modifier_weight = 0
        elif rank > max_weight_rank:
            modifier_weight = 1
        else:
            modifier_weight = rank / max_weight_rank

        return age_modifier**modifier_weight
