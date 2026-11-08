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
from scoring.runtime_components import write_runtime_component


def _fill(model, players, given):
    """`given` scores, with `model` scoring the players whose entry is None."""
    if given is None:
        return model.predict_many(players)
    missing = [p for p, score in zip(players, given) if score is None]
    legacy = iter(model.predict_many(missing) if missing else [])
    return [score if score is not None else next(legacy) for score in given]


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
        return self.score_many([player])[0]

    def score_many(self, players, batting_scores=None, fielding=None, running_scores=None):
        """Score a whole batch at once. Each attribute model runs a single
        batched prediction for the list (see `AttributeModel.predict_many`); the
        per-player fielding aggregation, modifiers and runtime-component writes
        are unchanged. Returns one
        `[overall, batting, fielding, running, best_position]` per player.

        `batting_scores`, `fielding` and `running_scores`, if given, come from
        elsewhere (engine v2's fitted models), aligned with `players`; the
        legacy models only score the players whose entry is None. A `fielding`
        entry is `(best_position_score, utility_bonus, best_position)`."""
        players = list(players)
        if not players:
            return []
        batting_scores = _fill(self.batting_model, players, batting_scores)
        running_scores = _fill(self.running_model, players, running_scores)
        fielding = fielding or [None] * len(players)
        missing = [p for p, f in zip(players, fielding) if f is None]
        fielding_by_position = {
            position: iter(model.predict_many(missing) if missing else [])
            for position, model in self.fielding_models_map.items()
        }

        results = []
        for i, player in enumerate(players):
            if fielding[i] is None:
                position_scores = {
                    position: next(fielding_by_position[position])
                    for position in self.fielding_models_map
                }
                [fielding_score, _, _, best_position] = self.__aggregate_fielding_score(
                    player, position_scores
                )
            else:
                best_score, utility, best_position = fielding[i]
                fielding_score = best_score + utility
                write_runtime_component(player.id, "batting.model.best_position_score", best_score)
                write_runtime_component(player.id, "batting.model.utility_bonus", utility)
            batting_score = batting_scores[i]
            running_score = running_scores[i]
            write_runtime_component(player.id, "batting.model.batting", batting_score)
            write_runtime_component(player.id, "batting.model.running", running_score)
            overall_score = (
                (batting_score * 0.73)
                + (fielding_score * 0.22)
                + (running_score * 0.05)
            )
            write_runtime_component(player.id, "batting.model.overall", overall_score)
            results.append(
                [
                    overall_score,
                    batting_score,
                    fielding_score,
                    running_score,
                    best_position,
                ]
            )
        return results

    def __aggregate_fielding_score(self, player, position_scores):
        [best_score, best_position] = best_position_score(position_scores)
        bonus = utility_bonus(position_scores)
        overall_score = best_score + bonus
        write_runtime_component(player.id, "batting.model.best_position_score", best_score)
        write_runtime_component(player.id, "batting.model.utility_bonus", bonus)
        return [overall_score, best_score, bonus, best_position]


def best_position_score(position_scores):
    best_position = None
    best_score = 0
    for position, score in position_scores.items():
        if score > best_score:
            best_score = score
            best_position = position
    return [best_score, best_position]

def utility_bonus(position_scores):
    """Legacy's bonus for positions a player can cover beyond his best one,
    from the per-position fielding scores."""
    has_ss_bonus = False
    has_cf_bonus = False
    has_rf_bonus = False
    has_c_bonus = False
    bonus_score = 0
    [best_score, best_position] = best_position_score(
        position_scores
    )

    if best_position == "C" and position_scores["C"] > 20:
        # treat C as a special bonus case
        bonus_score += min(position_scores["C"] * 0.03, 2)

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
