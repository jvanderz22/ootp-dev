from attribute_models.batting_attribute_model import BattingAttributeModel
from attribute_models.running_attribute_model import RunningAttributeModel
from attribute_models.second_base_attribute_model import SecondBaseAttributeModel
from attribute_models.center_field_attribute_model import CenterFieldAttributeModel
from attribute_models.left_field_attribute_model import LeftFieldAttributeModel
from attribute_models.right_field_attribute_model import RightFieldAttributeModel
from attribute_models.shortstop_attribute_model import ShortstopAttributeModel
from attribute_models.catcher_attribute_model import CatcherAttributeModel
from attribute_models.third_base_attribute_model import ThirdBaseAttributeModel
from attribute_models.first_base_attribute_model import FirstBaseAttributeModel


class PositionPlayerScorer:
    def __init__(self, type="potential"):
        self.batting_model = BattingAttributeModel(type)
        self.fielding_models_map = {
            "C": CatcherAttributeModel(),
            "1B": FirstBaseAttributeModel(),
            "2B": SecondBaseAttributeModel(),
            "SS": ShortstopAttributeModel(),
            "3B": ThirdBaseAttributeModel(),
            "CF": CenterFieldAttributeModel(),
            "RF": RightFieldAttributeModel(),
            "LF": LeftFieldAttributeModel(),
        }
        self.running_model = RunningAttributeModel()

    def score(self, player):
        [fielding_score, _, _, best_position] = self.__calculate_fielding_score(player)
        batting_score = self.batting_model.run(player)
        running_score = self.running_model.run(player)
        overall_score = (
            (batting_score * 0.71) + (fielding_score * 0.23) + (running_score * 0.06)
        )

        return [overall_score, batting_score, fielding_score]

    def __calculate_fielding_score(self, player):
        position_scores = {}
        for fielding_position in self.fielding_models_map.keys():
            model = self.fielding_models_map[fielding_position]
            position_scores[fielding_position] = model.run(player)
        [best_score, best_position] = self.__calculate_best_position_score(
            position_scores
        )
        utility_bonus = self.__calculate_utility_bonuses(position_scores)
        overall_score = best_score + utility_bonus
        return [overall_score, best_score, utility_bonus, best_position]

    def __calculate_best_position_score(self, position_scores):
        best_position = None
        best_position_score = 0
        for position, score in position_scores.items():
            if score > best_position_score:
                best_position_score = score
                best_position = position
        return [best_position_score, best_position]

    def __calculate_utility_bonuses(self, position_scores):
        has_ss_bonus = False
        has_cf_bonus = False
        has_rf_bonus = False
        bonus_score = 0
        [best_position_score, best_position] = self.__calculate_best_position_score(
            position_scores
        )
        if best_position == "SS":
            has_ss_bonus = True
        elif best_position == "CF":
            has_cf_bonus = True
        elif best_position == "RF":
            has_rf_bonus = True

        if has_ss_bonus is False and position_scores["SS"] > 20:
            has_ss_bonus = True
            bonus_score += min(position_scores["SS"] * 0.1, 3)

        if has_ss_bonus is False and position_scores["2B"] > 25:
            bonus_score += min(position_scores["2B"] * 0.06, 2)

        if position_scores["3B"] > 25:
            if has_ss_bonus:
                bonus_score += min(position_scores["3B"] * 0.02, 1)
            else:
                bonus_score += min(position_scores["3B"] * 0.06, 2)

        if has_cf_bonus is False and position_scores["CF"] > 25:
            has_cf_bonus = True
            bonus_score += min(position_scores["CF"] * 0.1, 4)

        if (
            has_cf_bonus is False
            and has_rf_bonus is False
            and position_scores["RF"] > 25
        ):
            has_rf_bonus = True
            bonus_score += min(position_scores["RF"] * 0.03, 2)

        if (
            has_cf_bonus is False
            and has_rf_bonus is False
            and position_scores["LF"] > 40
        ):
            has_rf_bonus = True
            bonus_score += position_scores["LF"] * 0.05
        return bonus_score
