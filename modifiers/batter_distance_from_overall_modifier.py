from modifiers.base_modifier import BaseModifier
from scoring.position_player_scorer import PositionPlayerScorer


class BatterDistanceFromOverallModifier(BaseModifier):
    overall_scorer = PositionPlayerScorer("overall")
    potential_scorer = PositionPlayerScorer()

    @classmethod
    def calculate_player_modifier(cls, player):
        [overall_score, overall_batting_score, _] = cls.overall_scorer.score(player)
        [potential_score, potential_batting_score, _] = cls.potential_scorer.score(
            player
        )
        if potential_batting_score == 0:
            return 1
        if overall_batting_score == 0:
            return 0.75

        diff_percentage = overall_batting_score / potential_batting_score
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
