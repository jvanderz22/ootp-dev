from modifiers.base_rank_modifier import BaseRankModifier


class RankGradiatedModel:

    def __init__(self, ranks, vals):
        if len(ranks) != len(vals):
            raise Exception("Ranks and vals must be same lenght")
        self.ranks = ranks
        self.vals = vals

    def rank(self, rank):
        greater_rank_index = None
        for i, set_rank in enumerate(self.ranks):
            if rank > set_rank:
                greater_rank_index = i
        if greater_rank_index is None:
            return self.vals[0]
        if greater_rank_index == len(self.ranks) - 1:
            return self.vals[-1]
        lesser_rank_val = self.ranks[greater_rank_index]
        greater_rank_val = self.ranks[greater_rank_index + 1]
        position_between = greater_rank_val - rank
        total_rank_diff = greater_rank_val - lesser_rank_val
        scale_factor = 1 - (position_between / total_rank_diff)

        total_val_diff = (
            self.vals[greater_rank_index + 1] - self.vals[greater_rank_index]
        )
        return total_val_diff * scale_factor + self.vals[greater_rank_index]


class DraftRankPersonalityModifier(BaseRankModifier):
    modifier_model = RankGradiatedModel(
        [10, 25, 50, 75, 100, 150, 200, 300, 350, 400],
        [0.02, 0.05, 0.1, 0.2, 0.6, 0.8, 0.9, 1, 1.3, 1.5],
    )

    @classmethod
    def calculate_player_modifier(cls, player, rank):
        personality_modifier = 1
        modifier_weight = cls.modifier_model.rank(rank)

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
