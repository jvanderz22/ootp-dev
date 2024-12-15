from attribute_models.relief_pitcher_attribute_model import ReliefPitcherAttributeModel
from attribute_models.starting_pitcher_attribute_model import (
    StartingPitcherAttributeModel,
)


# Lower the all RPs scores using this modifier
RP_OVERALL_MODIFIER = 0.7


rp_groundball_type_modifier_map = {
    "EX FB": 0.93,
    "FB": 1,
    "NEU": 1,
    "GB": 1.02,
    "EX GB": 1.05,
}

rp_stamina_modifier_map = {
    20: 0.87,
    25: 0.93,
    30: 0.96,
    35: 0.99,
    40: 1,
    45: 1,
    50: 1,
    55: 1.02,
    60: 1.04,
    65: 1.06,
    70: 1.06,
    75: 1.06,
    80: 1.06,
}

rp_best_pitch_value_modifier_map = {
    20: 0.81,
    25: 0.84,
    30: 0.88,
    35: 0.90,
    40: 0.93,
    45: 0.97,
    50: 0.99,
    55: 1,
    60: 1.02,
    65: 1.07,
    70: 1.15,
    75: 1.25,
    80: 1.30,
}

rp_second_pitch_value_modifier_map = {
    20: 0.81,
    25: 0.84,
    30: 0.89,
    35: 0.91,
    40: 0.94,
    45: 0.96,
    50: 0.98,
    55: 1,
    60: 1.02,
    65: 1.05,
    70: 1.1,
    75: 1.15,
    80: 1.2,
}

rp_third_pitch_value_modifier_map = {
    20: 1,
    25: 1,
    30: 1,
    35: 1,
    40: 1.02,
    45: 1.05,
    50: 1.08,
    55: 1.1,
    60: 1.1,
    65: 1.1,
    70: 1.15,
    75: 1.15,
    80: 1.15,
}


def calculate_rp_modifier(player, type="potential"):
    modifier = 1

    gb_type = player.groundball_type
    modifier *= rp_groundball_type_modifier_map[gb_type]

    stamina = player.stamina
    stamina_modifier = rp_stamina_modifier_map[stamina]
    pitches = player.get_pitches() if type == "potential" else player.get_ovr_pitches()

    if len(pitches) < 1:
        return 0

    first_pitch_modifier = rp_best_pitch_value_modifier_map[getattr(player, pitches[0])]
    second_pitch_modifier = 0.8
    if len(pitches) >= 2:
        second_pitch_modifier = rp_second_pitch_value_modifier_map[
            getattr(player, pitches[1])
        ]

    third_pitch_modifier = 1
    if len(pitches) >= 3:
        third_pitch_modifier = rp_third_pitch_value_modifier_map[
            getattr(player, pitches[2])
        ]

    total_rp_value_modifier = (
        stamina_modifier
        * first_pitch_modifier
        * second_pitch_modifier
        * third_pitch_modifier
    )
    # Apply potential starter bonus instead
    if int(stamina) >= 35 and len(pitches) >= 3 and getattr(player, pitches[2]) >= 40:
        total_rp_value_modifier = 1.4

    modifier *= total_rp_value_modifier

    home_run_risk_modifier = 1
    if player.movement < 45 and player.groundball_type == "EX FB":
        home_run_risk_modifier = 0.92

    modifier *= home_run_risk_modifier

    return modifier


sp_stamina_modifier_map = {
    20: 0.25,
    25: 0.25,
    30: 0.7,
    35: 0.85,
    40: 0.93,
    45: 0.97,
    50: 0.99,
    55: 1,
    60: 1.01,
    65: 1.01,
    70: 1.015,
    75: 1.02,
    80: 1.03,
}

sp_groundball_type_modifier_map = {
    "EX FB": 0.96,
    "FB": 1,
    "NEU": 1,
    "GB": 1.02,
    "EX GB": 1.05,
}


sp_best_pitch_value_modifier_map = {
    20: 0.92,
    25: 0.92,
    30: 0.92,
    35: 0.93,
    40: 0.945,
    45: 0.96,
    50: 0.98,
    55: 0.99,
    60: 1,
    65: 1.02,
    70: 1.05,
    75: 1.10,
    80: 1.15,
}


sp_second_pitch_value_modifier_map = {
    20: 0.82,
    25: 0.84,
    30: 0.86,
    35: 0.89,
    40: 0.92,
    45: 0.96,
    50: 0.98,
    55: 1,
    60: 1.03,
    65: 1.04,
    70: 1.07,
    75: 1.1,
    80: 1.15,
}


sp_third_pitch_value_modifier_map = {
    20: 0.7,
    25: 0.76,
    30: 0.81,
    35: 0.88,
    40: 0.92,
    45: 0.96,
    50: 1,
    55: 1.03,
    60: 1.06,
    65: 1.09,
    70: 1.11,
    75: 1.14,
    80: 1.2,
}


sp_fourth_pitch_value_modifier_map = {
    20: 0.92,
    25: 0.93,
    30: 0.94,
    35: 0.97,
    40: 0.99,
    45: 1,
    50: 1.01,
    55: 1.03,
    60: 1.045,
    65: 1.07,
    70: 1.09,
    75: 1.1,
    80: 1.2,
}

sp_fifth_pitch_value_modifier_map = {
    20: 1.04,
    25: 1.04,
    30: 1.04,
    35: 1.04,
    40: 1.04,
    45: 1.04,
    50: 1.04,
    55: 1.04,
    60: 1.04,
    65: 1.06,
    70: 1.1,
    75: 1.1,
    80: 1.2,
}


def calculate_sp_modifiers(player, type="potential"):
    modifier = 1

    gb_type = player.groundball_type
    gb_type_modifier = sp_groundball_type_modifier_map[gb_type]
    modifier *= gb_type_modifier

    stamina_modifier = sp_stamina_modifier_map[player.stamina]
    pitches = player.get_pitches() if type == "potential" else player.get_ovr_pitches()
    if len(pitches) < 1:
        return {"total_modifier": 0}
    first_pitch_modifier = sp_best_pitch_value_modifier_map[getattr(player, pitches[0])]
    second_pitch_modifier = 0.8
    if len(pitches) > 2:
        second_pitch_modifier = sp_second_pitch_value_modifier_map[
            getattr(player, pitches[1])
        ]
    third_pitch_modifier = 1
    if len(pitches) < 3:
        third_pitch_modifier = 0.35
    else:
        third_pitch_modifier = sp_third_pitch_value_modifier_map[
            getattr(player, pitches[2])
        ]

    fourth_pitch_modifier = 0.92
    if len(pitches) >= 4:
        fourth_pitch_modifier = sp_fourth_pitch_value_modifier_map[
            getattr(player, pitches[3])
        ]

    fifth_pitch_modifier = 1
    if len(pitches) >= 5:
        fifth_pitch_modifier = sp_fifth_pitch_value_modifier_map[
            getattr(player, pitches[4])
        ]

    total_sp_value_modifier = (
        stamina_modifier
        * first_pitch_modifier
        * second_pitch_modifier
        * third_pitch_modifier
        * fourth_pitch_modifier
        * fifth_pitch_modifier
    )
    # Treat SP as an RP instead
    if total_sp_value_modifier < 0.45:
        total_sp_value_modifier = 0.45

    modifier *= total_sp_value_modifier

    home_run_risk_modifier = 1
    if player.movement < 45 and player.groundball_type == "EX FB":
        home_run_risk_modifier = 0.9

    modifier *= home_run_risk_modifier
    return {
        "total_modifier": modifier,
        "gb_type_modifier": gb_type_modifier,
        "sp_value_modifier": total_sp_value_modifier,
        "home_run_risk_modifier": home_run_risk_modifier,
    }


class PitcherScorer:
    def __init__(
        self,
        type="potential",
        rp_multiplier=RP_OVERALL_MODIFIER,
    ):
        self.type = type
        self.sp_model = StartingPitcherAttributeModel(type)
        self.rp_model = ReliefPitcherAttributeModel(type)
        self.rp_modifier = rp_multiplier

    def score(self, player):
        position = player.position
        score = None
        if position == "RP" or position == "CL":
            relief_score = self.__calculate_rp_score(player)
            starting_score = self.__calculate_sp_score(player) * 0.8
            score = starting_score if starting_score > relief_score else relief_score
        else:
            starting_score = self.__calculate_sp_score(player)
            relief_score = self.__calculate_rp_score(player)
            score = starting_score if starting_score > relief_score else relief_score
        score = score if score > 0 else 0

        # Try to fix the batter/pitcher distribution
        score = self.apply_adjustment(score)
        return [score, starting_score, relief_score]

    def apply_adjustment(self, score):
        diff_from_65 = score - 65
        diff_exponent = -diff_from_65 / 750
        multiplier = score**diff_exponent

        additive_effect = 0
        if score > 10:
            # boost mid-tier pitcher scoring with an addition
            additive_effect = max(-diff_from_65 / 4, 0)
        return multiplier * score + additive_effect

    def __calculate_sp_score(self, player):
        base_score = self.sp_model.run(player)
        modifiers = calculate_sp_modifiers(player, self.type)
        score = base_score * modifiers["total_modifier"]
        return score

    def __calculate_rp_score(self, player):
        rp_score = self.rp_model.run(player)
        rp_modifier = calculate_rp_modifier(player, self.type)
        return rp_score * rp_modifier * self.rp_modifier
