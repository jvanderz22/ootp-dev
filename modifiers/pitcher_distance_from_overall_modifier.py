from modifiers.base_modifier import BaseModifier
from scoring.pitcher_score import PitcherScorer


class PitcherDistanceFromOverallModifier(BaseModifier):
    overall_scorer = PitcherScorer("overall")
    potential_scorer = PitcherScorer()

    @classmethod
    def calculate_player_modifier(cls, player):
        overall_score = cls.overall_scorer.score(player)
        potential_score = cls.potential_scorer.score(player)
        if potential_score == 0:
            return 1
        if overall_score == 0:
            return 0.75

        diff_percentage = overall_score / potential_score
        if diff_percentage > 0.95:
            return 1
        elif diff_percentage > 0.8:
            return 0.97
        elif diff_percentage > 0.6:
            return 0.94
        elif diff_percentage > 0.4:
            return 0.9
        elif diff_percentage > 0.2:
            return 0.88
        elif diff_percentage > 0.1:
            return 0.82
        return 0.75
