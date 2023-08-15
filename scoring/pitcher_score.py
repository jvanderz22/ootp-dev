from attribute_models.relief_pitcher_attribute_model import ReliefPitcherAttributeModel
from attribute_models.starting_pitcher_attribute_model import (
    StartingPitcherAttributeModel,
)


PITCHER_EXPONENT = 0.40
PITCHER_MULTIPLIER = 12


rp_groundball_type_modifier_map = {
    "EX FB": 0.93,
    "FB": 1,
    "NEU": 1,
    "GB": 1.02,
    "EX GB": 1.07,
}

rp_stamina_modifier_map = {
    20: 0.87,
    25: 0.94,
    30: 0.97,
    35: 1,
    40: 1,
    45: 1.05,
    50: 1.05,
    55: 1.05,
    60: 1.05,
    65: 1.05,
    70: 1.05,
    75: 1.05,
    80: 1.05,
}

rp_third_pitch_value_modifier_map = {
    20: 1,
    25: 1,
    30: 1.1,
    35: 1.1,
    40: 1.15,
    45: 1.15,
    50: 1.15,
    55: 1.2,
    60: 1.2,
    65: 1.2,
    70: 1.2,
    75: 1.2,
    80: 1.2,
}


def calculate_rp_modifier(player, type="potential"):
    # Base rp score is lower
    modifier = 0.60

    gb_type = player.groundball_type
    modifier *= rp_groundball_type_modifier_map[gb_type]

    stamina = player.stamina
    stamina_modifier = rp_stamina_modifier_map[stamina]
    pitches = player.get_pitches() if type == "potential" else player.get_ovr_pitches()
    third_pitch_modifier = 1
    if len(pitches) >= 3:
        third_pitch_modifier = rp_third_pitch_value_modifier_map[
            getattr(player, pitches[2])
        ]

    total_rp_value_modifier = stamina_modifier * third_pitch_modifier
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
    20: 0.35,
    25: 0.35,
    30: 0.4,
    35: 0.6,
    40: 0.85,
    45: 0.95,
    50: 0.98,
    55: 1,
    60: 1.02,
    65: 1.03,
    70: 1.04,
    75: 1.04,
    80: 1.05,
}

sp_groundball_type_modifier_map = {
    "EX FB": 0.96,
    "FB": 1,
    "NEU": 1,
    "GB": 1.03,
    "EX GB": 1.08,
}

sp_third_pitch_value_modifier_map = {
    20: 0.35,
    25: 0.35,
    30: 0.4,
    35: 0.6,
    40: 0.85,
    45: 1,
    50: 1.03,
    55: 1.06,
    60: 1.09,
    65: 1.1,
    70: 1.1,
    75: 1.1,
    80: 1.1,
}

sp_fourth_pitch_value_modifier_map = {
    20: 0.97,
    25: 0.97,
    30: 0.97,
    35: 1,
    40: 1,
    45: 1.03,
    50: 1.05,
    55: 1.05,
    60: 1.1,
    65: 1.1,
    70: 1.2,
    75: 1.2,
    80: 1.2,
}

sp_fifth_pitch_value_modifier_map = {
    20: 1,
    25: 1,
    30: 1.01,
    35: 1.02,
    40: 1.03,
    45: 1.03,
    50: 1.05,
    55: 1.05,
    60: 1.05,
    65: 1.1,
    70: 1.2,
    75: 1.2,
    80: 1.2,
}


def calculate_sp_modifiers(player, type="potential"):
    modifier = 1

    gb_type = player.groundball_type
    gb_type_modifier = sp_groundball_type_modifier_map[gb_type]
    modifier *= gb_type_modifier

    stamina_modifier = sp_stamina_modifier_map[player.stamina]
    pitches = player.get_pitches() if type == "potential" else player.get_ovr_pitches()
    third_pitch_modifier = 1
    if len(pitches) < 3:
        third_pitch_modifier = 0.35
    else:
        third_pitch_modifier = sp_third_pitch_value_modifier_map[
            getattr(player, pitches[2])
        ]

    fourth_pitch_modifier = 0.97
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
    def __init__(self, type="potential"):
        self.type = type
        self.sp_model = StartingPitcherAttributeModel(type)
        self.rp_model = ReliefPitcherAttributeModel(type)

    def score(self, player):
        position = player.position
        if position == "RP" or position == "CL":
            score = self.__calculate_rp_score(player)
        else:
            score = self.__calculate_sp_score(player)
        score = score if score > 0 else 0
        # Try to fix the batter/pitcher distribution
        score = (score**PITCHER_EXPONENT) * PITCHER_MULTIPLIER
        return score

    def __calculate_sp_score(self, player):
        base_score = self.sp_model.run(player)
        modifiers = calculate_sp_modifiers(player, self.type)
        score = base_score * modifiers["total_modifier"]
        return score

    def __calculate_rp_score(self, player):
        rp_score = self.rp_model.run(player)
        rp_modifier = calculate_rp_modifier(player, self.type)
        return rp_score * rp_modifier
