from attribute_models.batting_attribute_model import BattingAttributeModel
from attribute_models.running_attribute_model import RunningAttributeModel
from attribute_models.second_base_attribute_model import SecondBaseAttributeModel
from attribute_models.center_field_attribute_model import CenterFieldAttributeModel
from attribute_models.left_field_attribute_model import LeftFieldAttributeModel
from attribute_models.right_field_attribute_model import RightFieldAttributeModel
from attribute_models.shortstop_attribute_model import ShortstopAttributeModel
from attribute_models.catcher_attribute_model import CatcherAttributeModel
from attribute_models.third_base_attribute_model import ThirdBaseAttributeModel


def create_fielding_models_map():
    return {
        "C": CatcherAttributeModel(),
        "2B": SecondBaseAttributeModel(),
        "SS": ShortstopAttributeModel(),
        "3B": ThirdBaseAttributeModel(),
        "CF": CenterFieldAttributeModel(),
        "RF": RightFieldAttributeModel(),
        "LF": LeftFieldAttributeModel(),
    }


batting_model = BattingAttributeModel()
fielding_models_map = create_fielding_models_map()
running_model = RunningAttributeModel()


def calculate_best_position_score(position_scores):
    best_position = None
    best_position_score = 0
    for position, score in position_scores.items():
        if score > best_position_score:
            best_position_score = score
            best_position = position
    return [best_position_score, best_position]


def calculate_utility_bonuses(position_scores):
    has_ss_bonus = False
    has_cf_bonus = False
    has_rf_bonus = False
    bonus_score = 0
    [best_position_score, best_position] = calculate_best_position_score(
        position_scores
    )
    if best_position == "SS":
        has_ss_bonus = True
    elif best_position == "CF":
        has_cf_bonus = True
    elif best_position == "RF":
        has_rf_bonus = True

    if has_ss_bonus is False and position_scores["SS"] > 40:
        has_ss_bonus = True
        bonus_score += position_scores["SS"] * 0.3

    if has_ss_bonus is False and position_scores["2B"] > 40:
        bonus_score += position_scores["2B"] * 0.2

    if position_scores["3B"] > 40:
        if has_ss_bonus:
            bonus_score += position_scores["3B"] * 0.03
        else:
            bonus_score += position_scores["3B"] * 0.1

    if has_cf_bonus is False and position_scores["CF"] > 40:
        has_cf_bonus = True
        bonus_score += position_scores["CF"] * 0.25

    if has_cf_bonus is False and has_rf_bonus is False and position_scores["RF"] > 40:
        has_rf_bonus = True
        bonus_score += position_scores["RF"] * 0.10

    if has_cf_bonus is False and has_rf_bonus is False and position_scores["LF"] > 40:
        has_rf_bonus = True
        bonus_score += position_scores["LF"] * 0.05
    return bonus_score


def calculate_fielding_score(player):
    position_scores = {}
    for fielding_position in fielding_models_map.keys():
        model = fielding_models_map[fielding_position]
        position_scores[fielding_position] = model.run(player)
    [best_score, best_position] = calculate_best_position_score(position_scores)
    utility_bonus = calculate_utility_bonuses(position_scores)
    overall_score = best_score + utility_bonus
    return [overall_score, best_score, utility_bonus, best_position]


def calculate_position_player_score(player):
    [fielding_score, _, _, best_position] = calculate_fielding_score(player)
    batting_score = batting_model.run(player)
    running_score = running_model.run(player)
    overall_score = (
        (batting_score * 0.76) + (fielding_score * 0.25) + (running_score * 0.04)
    )

    # if best_position == "C" and fielding_score > 40:
    #     overall_modifier *= 1.07
    # if best_position == "SS" and fielding_score > 70:
    #     overall_modifier *= 1.07
    # if best_position == "CF" and fielding_score > 70:
    #     overall_modifier *= 1.07

    return [overall_score, batting_score, fielding_score]