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
