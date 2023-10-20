from modifiers.base_rank_modifier import BaseRankModifier


class DraftRankPersonalityModifier(BaseRankModifier):
    @classmethod
    def calculate_player_modifier(cls, player, rank):
        modifier_weight = 0
        personality_modifier = 1

        if rank < 100:
            pass
        elif rank < 150:
            modifier_weight = 0.6
        elif rank < 200:
            modifier_weight = 0.8
        elif rank < 300:
            modifier_weight = 0.9
        else:
            modifier_weight = 1

        bad_personalities = 0
        if player.work_ethic == "L":
            bad_personalities += 1
        if player.intelligence == "L":
            bad_personalities += 1
        if player.adaptibility == "L":
            bad_personalities += 1
        if player.loyalty == "L":
            bad_personalities += 1
        if player.leadership == "L":
            bad_personalities += 1
        if player.greed == "H":
            bad_personalities += 1

        if bad_personalities > 5:
            personality_modifier *= 0.5
        elif bad_personalities > 4:
            personality_modifier *= 0.7
        elif bad_personalities > 3:
            personality_modifier *= 0.92

        if player.leadership == "H":
            personality_modifier *= 1.2
        if player.work_ethic == "H" and player.intelligence == "H":
            personality_modifier *= 1.2

        return personality_modifier**modifier_weight
