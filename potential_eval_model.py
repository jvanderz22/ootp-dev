import numpy as np
from sklearn.preprocessing import PolynomialFeatures
from sklearn import linear_model
import re
import csv
from constants import USE_PITCHER_MODIFIER, PITCHER_EXPONENT, PITCHER_MULTIPLIER
from draft_class_files import (
    get_draft_class_eval_model_file,
    get_draft_class_data_file,
)

PLAYER_FIELDS = {
    "position": "POS",
    "id": "ID",
    "name": "Name",
    "age": "Age",
    "potential": "POT",
    "demand": "DEM",
    "signability": "Sign",
    "throwHand": "T",
    "batHand": "B",
    "injuryProne": "Prone",
    "intelligence": "INT",
    "workEthic": "WE",
    "leadership": "LEA",
    "loyalty": "LOY",
    "adaptibility": "AD",
    "greed": "GRE",
    "contact": "CON P",
    "gap": "GAP P",
    "power": "POW P",
    "eye": "EYE P",
    "k": "K P",
    "speed": "SPE",
    "steal": "STE",
    "runningAbility": "RUN",
    "cArm": "C ARM",
    "cAbility": "C ABI",
    "ifRange": "IF RNG",
    "ifArm": "IF ARM",
    "ifError": "IF ERR",
    "turnDp": "TDP",
    "ofRange": "OF RNG",
    "ofArm": "OF ARM",
    "ofError": "OF ERR",
    "stuff": "STU P",
    "movement": "MOV P",
    "control": "CONT P",
    "stamina": "STM",
    "groundball_type": "G/F",
    "fastball": "FBP",
    "changeup": "CHP",
    "curveball": "CBP",
    "slider": "SLP",
    "sinker": "SIP",
    "splitter": "SPP",
    "cutter": "CTP",
    "forkball": "FOP",
    "circlechange": "CCP",
    "screwball": "SCP",
    "knuckleball": "KNP",
    "knucklecurve": "KCP",
}

pitch_fields = [
    "fastball",
    "changeup",
    "curveball",
    "slider",
    "sinker",
    "splitter",
    "cutter",
    "forkball",
    "circlechange",
    "screwball",
    "knuckleball",
    "knucklecurve",
]


fielding_model_configs = [
    {
        "model_type": "C",
        "file_path": "./training_data/OOTP Models - C data.csv",
        "rightHandedOnly": True,
        "fields": ["C Ability", "C Arm"],
        "fields_mapping": {
            "C Arm": PLAYER_FIELDS["cArm"],
            "C Ability": PLAYER_FIELDS["cAbility"],
        },
    },
    {
        "model_type": "2B",
        "file_path": "./training_data/OOTP Models - 2B data.csv",
        "rightHandedOnly": True,
        "fields": [
            "Range",
            "Arm",
            "Error",
            "Dp",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ifRange"],
            "Arm": PLAYER_FIELDS["ifArm"],
            "Error": PLAYER_FIELDS["ifError"],
            "Dp": PLAYER_FIELDS["turnDp"],
        },
    },
    {
        "model_type": "SS",
        "file_path": "./training_data/OOTP Models - SS data.csv",
        "rightHandedOnly": True,
        "fields": [
            "Range",
            "Arm",
            "Error",
            "Dp",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ifRange"],
            "Arm": PLAYER_FIELDS["ifArm"],
            "Error": PLAYER_FIELDS["ifError"],
            "Dp": PLAYER_FIELDS["turnDp"],
        },
    },
    {
        "model_type": "3B",
        "file_path": "./training_data/OOTP Models - 3B data.csv",
        "rightHandedOnly": True,
        "fields": [
            "Range",
            "Arm",
            "Error",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ifRange"],
            "Arm": PLAYER_FIELDS["ifArm"],
            "Error": PLAYER_FIELDS["ifError"],
        },
    },
    {
        "model_type": "CF",
        "file_path": "./training_data/OOTP Models - CF data.csv",
        "fields": [
            "Range",
            "Arm",
            "Error",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ofRange"],
            "Arm": PLAYER_FIELDS["ofArm"],
            "Error": PLAYER_FIELDS["ofError"],
        },
    },
    {
        "model_type": "RF",
        "file_path": "./training_data/OOTP Models - RF data.csv",
        "fields": [
            "Range",
            "Arm",
            "Error",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ofRange"],
            "Arm": PLAYER_FIELDS["ofArm"],
            "Error": PLAYER_FIELDS["ofError"],
        },
    },
    {
        "model_type": "LF",
        "file_path": "./training_data/OOTP Models - LF data.csv",
        "fields": [
            "Range",
            "Arm",
            "Error",
        ],
        "fields_mapping": {
            "Range": PLAYER_FIELDS["ofRange"],
            "Arm": PLAYER_FIELDS["ofArm"],
            "Error": PLAYER_FIELDS["ofError"],
        },
    },
]

batting_model_config = {
    "model_type": "batting",
    "file_path": "./training_data/OOTP Models - Batter data.csv",
    "fields": ["Contact", "Gap", "Power", "Eye", "K"],
    "fields_mapping": {
        "Contact": PLAYER_FIELDS["contact"],
        "Gap": PLAYER_FIELDS["gap"],
        "Power": PLAYER_FIELDS["power"],
        "Eye": PLAYER_FIELDS["eye"],
        "K": PLAYER_FIELDS["k"],
    },
}

running_model_config = {
    "model_type": "running",
    "file_path": "./training_data/OOTP Models - Running data.csv",
    "fields": [
        "Speed",
        "Steal",
        "Baserunning",
    ],
    "fields_mapping": {
        "Speed": PLAYER_FIELDS["speed"],
        "Steal": PLAYER_FIELDS["steal"],
        "Baserunning": PLAYER_FIELDS["runningAbility"],
    },
}

sp_model_config = {
    "model_type": "SP",
    "file_path": "./training_data/OOTP Models - SP data.csv",
    "fields": [
        "Stuff",
        "Movement",
        "Control",
    ],
    "fields_mapping": {
        "Stuff": PLAYER_FIELDS["stuff"],
        "Movement": PLAYER_FIELDS["movement"],
        "Control": PLAYER_FIELDS["control"],
    },
}

rp_model_config = {
    "model_type": "SP",
    "file_path": "./training_data/OOTP Models - RP data.csv",
    "fields": [
        "Stuff",
        "Movement",
        "Control",
    ],
    "fields_mapping": {
        "Stuff": PLAYER_FIELDS["stuff"],
        "Movement": PLAYER_FIELDS["movement"],
        "Control": PLAYER_FIELDS["control"],
    },
}


def create_model(model_config):
    model_properties = model_config["fields"]
    independent_variables = []
    y = []
    with open(model_config["file_path"], newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for line in reader:
            independent_line_variables = [int(line[prop]) for prop in model_properties]
            independent_variables.append(independent_line_variables)
            y.append(int(line["Ovr"]))

    # generate a model of polynomial features
    poly = PolynomialFeatures(degree=len(model_properties))
    # transform the x data for proper fitting (for single variable type it returns,[1,x,x**2])
    x = poly.fit_transform(independent_variables)
    # generate the regression object
    clf = linear_model.LinearRegression(positive=True)
    # preform the actual regression
    clf.fit(x, y)
    return clf


def create_fielding_models_map():
    fielding_models = {}
    for model_config in fielding_model_configs:
        model = create_model(model_config)
        fielding_models[model_config["model_type"]] = {
            "model": model,
            "model_config": model_config,
        }
    return fielding_models


def create_batting_model():
    return create_model(batting_model_config)


def create_running_model():
    return create_model(running_model_config)


def create_sp_model():
    return create_model(sp_model_config)


def create_rp_model():
    return create_model(rp_model_config)


# Should be moved to some scoring class singleton I guess
batting_model = create_batting_model()
fielding_models_map = create_fielding_models_map()
running_model = create_running_model()
sp_model = create_sp_model()
rp_model = create_rp_model()


def run_model_for_player(model, model_config, player):
    player_attrs = [
        int(player[model_config["fields_mapping"][field]])
        for field in model_config["fields"]
    ]
    poly_features = PolynomialFeatures(degree=len(player_attrs))
    # transform the prediction to fit the model type
    fit_predict_ = poly_features.fit_transform([player_attrs])
    return model.predict(fit_predict_)[0]


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
        model = fielding_models_map[fielding_position]["model"]
        model_config = fielding_models_map[fielding_position]["model_config"]
        if player[PLAYER_FIELDS["throwHand"]] != "R" and model_config.get(
            "rightHandedOnly"
        ):
            position_scores[fielding_position] = 0

        position_scores[fielding_position] = run_model_for_player(
            model, model_config, player
        )
    [best_score, best_position] = calculate_best_position_score(position_scores)
    utility_bonus = calculate_utility_bonuses(position_scores)
    overall_score = best_score + utility_bonus
    return [overall_score, best_score, utility_bonus, best_position]


def calculate_batting_score(player):
    score = run_model_for_player(batting_model, batting_model_config, player)
    return score if score > 0 else 0


def calculate_running_score(player):
    score = run_model_for_player(running_model, running_model_config, player)
    return score if score > 0 else 0


def calculate_personality_modifier(player):
    modifier = 1
    intelligence = player[PLAYER_FIELDS["intelligence"]]
    if intelligence == "High":
        modifier *= 1.05
    elif intelligence == "Low":
        modifier *= 0.9

    workEthic = player[PLAYER_FIELDS["workEthic"]]
    if workEthic == "High":
        modifier *= 1.05
    elif workEthic == "Low":
        modifier *= 0.9

    return modifier


age_modifiers = {17: 1.05, 18: 1.05, 19: 1.02, 20: 1, 21: 1, 22: 0.99, 23: 0.93}


def calculate_age_modifier(player):
    age = int(player[PLAYER_FIELDS["age"]])
    return age_modifiers[age]


def calculate_position_player_modifier(player):
    modifier = 1
    if player[PLAYER_FIELDS["batHand"]] == "S":
        modifier *= 1.03

    injuryProne = player[PLAYER_FIELDS["injuryProne"]]
    if injuryProne == "Durable":
        modifier *= 1.05
    elif injuryProne == "Fragile":
        modifier *= 0.8

    modifier *= calculate_personality_modifier(player)

    modifier *= calculate_age_modifier(player)

    return modifier


def calculate_position_player_score(player):
    [fielding_score, _, _, best_position] = calculate_fielding_score(player)
    batting_score = calculate_batting_score(player)
    running_score = calculate_running_score(player)
    overall_score = (
        (batting_score * 0.71) + (fielding_score * 0.3) + (running_score * 0.04)
    )
    overall_modifier = calculate_position_player_modifier(player)

    if best_position == "C" and fielding_score > 40:
        overall_modifier *= 1.07
    if best_position == "SS" and fielding_score > 70:
        overall_modifier *= 1.07
    if best_position == "CF" and fielding_score > 70:
        overall_modifier *= 1.07

    overall_score = overall_score * overall_modifier
    return [overall_score, batting_score, fielding_score]


def find_pitches(player):
    pitches = []
    for field in pitch_fields:
        try:
            pitch_attr = int(player[PLAYER_FIELDS[field]])
            pitches.append(pitch_attr)
        except ValueError:
            pass
    return sorted(pitches, reverse=True)


rp_groundball_type_modifier_map = {
    "EX FB": 0.93,
    "FB": 1,
    "NEU": 1,
    "GB": 1.05,
    "EX GB": 1.1,
}

rp_stamina_modifier_map = {
    "20": 0.93,
    "25": 0.96,
    "30": 0.98,
    "35": 1,
    "40": 1,
    "45": 1.05,
    "50": 1.05,
    "55": 1.05,
    "60": 1.05,
    "65": 1.05,
    "70": 1.05,
    "75": 1.05,
    "80": 1.05,
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


def calculate_rp_modifier(player):
    # Base rp score is lower
    modifier = 0.60
    injuryProne = player[PLAYER_FIELDS["injuryProne"]]
    if injuryProne == "Durable":
        modifier *= 1.1
    elif injuryProne == "Fragile":
        modifier *= 0.7

    gb_type = player[PLAYER_FIELDS["groundball_type"]]
    modifier *= rp_groundball_type_modifier_map[gb_type]

    stamina = player[PLAYER_FIELDS["stamina"]]
    stamina_modifier = rp_stamina_modifier_map[stamina]
    pitches = find_pitches(player)
    third_pitch_modifier = 1
    if len(pitches) >= 3:
        third_pitch_modifier = rp_third_pitch_value_modifier_map[pitches[2]]

    total_rp_value_modifier = stamina_modifier * third_pitch_modifier
    # Apply potential starter bonus instead
    if int(stamina) >= 35 and len(pitches) >= 3 and pitches[2] >= 40:
        total_rp_value_modifier = 1.4

    modifier *= total_rp_value_modifier

    home_run_risk_modifier = 1
    if (
        int(player[PLAYER_FIELDS["movement"]]) < 45
        and player[PLAYER_FIELDS["groundball_type"]] == "EX FB"
    ):
        home_run_risk_modifier = 0.92

    modifier *= home_run_risk_modifier

    modifier *= calculate_personality_modifier(player)
    return modifier


def calculate_rp_score(player):
    rp_score = run_model_for_player(rp_model, rp_model_config, player)
    rp_modifier = calculate_rp_modifier(player)
    return rp_score * rp_modifier


sp_stamina_modifier_map = {
    "20": 0.35,
    "25": 0.35,
    "30": 0.4,
    "35": 0.6,
    "40": 0.85,
    "45": 0.95,
    "50": 0.98,
    "55": 1,
    "60": 1.02,
    "65": 1.03,
    "70": 1.04,
    "75": 1.04,
    "80": 1.05,
}

sp_groundball_type_modifier_map = {
    "EX FB": 0.85,
    "FB": 1,
    "NEU": 1,
    "GB": 1.1,
    "EX GB": 1.2,
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


def calculate_sp_modifiers(player):
    modifier = 1

    injury_prone = player[PLAYER_FIELDS["injuryProne"]]
    injury_prone_modifier = 1

    if injury_prone == "Durable":
        injury_prone_modifier = 1.2
    elif injury_prone == "Fragile":
        injury_prone_modifier *= 0.6
    modifier *= injury_prone_modifier

    gb_type = player[PLAYER_FIELDS["groundball_type"]]
    gb_type_modifier = sp_groundball_type_modifier_map[gb_type]
    modifier *= gb_type_modifier

    stamina_modifier = sp_stamina_modifier_map[player[PLAYER_FIELDS["stamina"]]]
    pitches = find_pitches(player)
    third_pitch_modifier = 1
    if len(pitches) < 3:
        third_pitch_modifier = 0.35
    else:
        third_pitch_modifier = sp_third_pitch_value_modifier_map[pitches[2]]

    fourth_pitch_modifier = 0.97
    if len(pitches) >= 4:
        fourth_pitch_modifier = sp_fourth_pitch_value_modifier_map[pitches[3]]

    fifth_pitch_modifier = 1
    if len(pitches) >= 5:
        fifth_pitch_modifier = sp_fifth_pitch_value_modifier_map[pitches[4]]

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
    if (
        int(player[PLAYER_FIELDS["movement"]]) < 45
        and player[PLAYER_FIELDS["groundball_type"]] == "EX FB"
    ):
        home_run_risk_modifier = 0.9

    modifier *= home_run_risk_modifier

    personality_modifier = calculate_personality_modifier(player)
    age_modifier = calculate_age_modifier(player)
    modifier *= personality_modifier
    modifier *= age_modifier
    return {
        "total_modifier": modifier,
        "injury_prone_modifier": injury_prone_modifier,
        "gb_type_modifier": gb_type_modifier,
        "sp_value_modifier": total_sp_value_modifier,
        "home_run_risk_modifier": home_run_risk_modifier,
        "personality_modifier": personality_modifier,
        "age_modifier": age_modifier,
    }


def calculate_sp_score(player):
    base_score = run_model_for_player(sp_model, sp_model_config, player)
    modifiers = calculate_sp_modifiers(player)
    score = base_score * modifiers["total_modifier"]
    return score


def calculate_pitcher_score(player):
    position = player[PLAYER_FIELDS["position"]]
    if position == "RP" or position == "CL":
        score = calculate_rp_score(player)
    else:
        score = calculate_sp_score(player)
    # Try to fix the batter/pitcher distribution by round
    score = score if score > 0 else 0
    if USE_PITCHER_MODIFIER:
        score = (score**PITCHER_EXPONENT) * PITCHER_MULTIPLIER
    return score


def aggregate_pitcher_batter_scores(batter_score, pitcher_score):
    high_score = batter_score if batter_score > pitcher_score else pitcher_score
    low_score = batter_score if batter_score < pitcher_score else pitcher_score
    total_score = high_score
    # Add a bonus for potential two way players
    if (high_score - low_score) < (high_score / 2):
        total_score += low_score * 0.25
    return total_score


def parse_demand(demand):
    is_thousands = demand[-1] == "k"
    is_millions = demand[-1] == "m"
    if not is_thousands and not is_millions:
        raise ValueError("Invalid Demand", demand)
    demand_as_number = int(re.sub("[^0-9]", "", demand))
    return demand_as_number * 1000 if is_thousands else demand_as_number * 100000


def calculate_adjusted_score(scored_player, player):
    raw_ranking = scored_player["raw_ranking"]
    raw_score = scored_player["raw_overall_score"]
    demand_adjusted_score = calculate_demand_adjusted_score(
        raw_ranking,
        scored_player["demand"],
        raw_score,
    )
    return calculate_personality_adjusted_score(
        raw_ranking, demand_adjusted_score, player
    )


def calculate_personality_adjusted_score(ranking, score, player):
    leadership = player[PLAYER_FIELDS["leadership"]]
    adaptibility = player[PLAYER_FIELDS["adaptibility"]]
    greed = player[PLAYER_FIELDS["greed"]]
    work_ethic = player[PLAYER_FIELDS["workEthic"]]
    intelligence = player[PLAYER_FIELDS["intelligence"]]
    loyalty = player[PLAYER_FIELDS["loyalty"]]
    modifier_weight = 0
    personality_modifier = 1

    if ranking < 100:
        pass
    elif ranking < 200:
        modifier_weight = 0.6
    elif ranking < 300:
        modifier_weight = 0.8
    elif ranking < 400:
        modifier_weight = 0.9
    else:
        modifier_weight = 1

    bad_personalities = 0
    if work_ethic == "Low":
        bad_personalities += 1
    if intelligence == "Low":
        bad_personalities += 1
    if adaptibility == "Low":
        bad_personalities += 1
    if loyalty == "Low":
        bad_personalities += 1
    if leadership == "Low":
        bad_personalities += 1
    if greed == "High":
        bad_personalities += 1

    if bad_personalities > 5:
        personality_modifier *= 0.5
    elif bad_personalities > 4:
        personality_modifier *= 0.7
    elif bad_personalities > 3:
        personality_modifier *= 0.92

    if leadership == "High":
        personality_modifier *= 1.2
    if work_ethic == "High" and intelligence == "High":
        personality_modifier *= 1.2

    total_modifier = personality_modifier**modifier_weight

    return score * total_modifier


def create_demand_modifier_model(x, y):
    poly = PolynomialFeatures(degree=1)
    # transform the x data for proper fitting (for single variable type it returns,[1,x,x**2])
    fit_x = poly.fit_transform(x)
    clf = linear_model.LinearRegression(positive=True)
    # preform the actual regression
    # clf.fit(fit_x, y)
    reg = linear_model.LinearRegression()
    reg.fit(x, y)
    return reg


def run_demand_model(model, minimum_modifier, value):
    # poly_features = PolynomialFeatures(degree=1)
    # transform the prediction to fit the model type
    # fit_predict_ = poly_features.fit_transform([[value]])
    max_val = max(model.predict([[value]])[0], minimum_modifier)
    return min(max_val, 1)


base_modifier_min = 0.4
lt_20_min = 0.85
lt_20_ranking_demand_model = create_demand_modifier_model(
    [[8000000], [10000000]], [1, 0.85]
)

lt_30_min = 0.82
lt_30_ranking_demand_model = create_demand_modifier_model(
    [[7000000], [9000000]], [1, 0.82]
)

lt_60_min = 0.45
lt_60_ranking_demand_model = create_demand_modifier_model(
    [[1300000], [2800000], [5500000], [9000000]], [1, 0.9, 0.65, 0.45]
)

lt_100_ranking_demand_model = create_demand_modifier_model(
    [[750000], [950000], [1700000], [3500000]], [1, 0.95, 0.8, 0.4]
)

lt_150_ranking_demand_model = create_demand_modifier_model(
    [[700000], [850000], [1000000], [2500000]], [1, 0.95, 0.8, 0.4]
)

lt_250_ranking_demand_model = create_demand_modifier_model(
    [[450000], [500000], [700000], [1000000]], [1, 0.95, 0.7, 0.4]
)

gt_250_ranking_demand_model = create_demand_modifier_model(
    [[250000], [350000], [550000]], [1, 0.8, 0.4]
)


def calculate_demand_adjusted_score(ranking, demand, score):
    if demand == "Slot":
        return score
    if demand == "Impossible":
        return score * base_modifier_min
    parsed_demand = parse_demand(demand)
    if ranking < 10:
        return score
    elif ranking < 20:
        modifier = run_demand_model(
            lt_20_ranking_demand_model, lt_20_min, parsed_demand
        )
        return score * modifier
    elif ranking < 30:
        modifier = run_demand_model(
            lt_30_ranking_demand_model, lt_30_min, parsed_demand
        )
        return score * modifier
    elif ranking < 60:
        modifier = run_demand_model(
            lt_60_ranking_demand_model, lt_60_min, parsed_demand
        )
        return score * modifier
    elif ranking < 100:
        modifier = run_demand_model(
            lt_100_ranking_demand_model, base_modifier_min, parsed_demand
        )
        return score * modifier
    elif ranking < 150:
        modifier = run_demand_model(
            lt_150_ranking_demand_model, base_modifier_min, parsed_demand
        )
        return score * modifier
    elif ranking < 250:
        modifier = run_demand_model(
            lt_250_ranking_demand_model, base_modifier_min, parsed_demand
        )
        return score * modifier
    else:
        modifier = run_demand_model(
            gt_250_ranking_demand_model, base_modifier_min, parsed_demand
        )
        return score * modifier


def score_players():
    # Player should probably be a class
    output_field_names = [
        "ranking",
        "id",
        "name",
        "position",
        "age",
        "position_player_score",
        "fielding_score_component",
        "batting_score_component",
        "pitcher_score",
        "overall_score",
        "in_game_potential",
        "demand",
        "raw_overall_score",
        "raw_ranking",
    ]
    scored_players = []
    all_players = {}
    with open(get_draft_class_data_file(), newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        best_pitcher_score = 0
        best_position_player_score = 0
        for i, player in enumerate(reader):
            all_players[player[PLAYER_FIELDS["id"]]] = player
            [
                position_player_score,
                batting_score,
                fielding_score,
            ] = calculate_position_player_score(player)
            pitcher_score = calculate_pitcher_score(player)
            if pitcher_score > best_pitcher_score:
                best_pitcher_score = pitcher_score
            if position_player_score > best_position_player_score:
                best_position_player_score = position_player_score
            scored_player = {
                "id": player[PLAYER_FIELDS["id"]],
                "name": player[PLAYER_FIELDS["name"]],
                "position": player[PLAYER_FIELDS["position"]],
                "age": player[PLAYER_FIELDS["age"]],
                "batting_score_component": round(batting_score, 2),
                "fielding_score_component": round(fielding_score, 2),
                "position_player_score": round(position_player_score, 2),
                "pitcher_score": round(pitcher_score, 2),
                "raw_overall_score": aggregate_pitcher_batter_scores(
                    position_player_score, pitcher_score
                ),
                "in_game_potential": player[PLAYER_FIELDS["potential"]],
                "demand": player[PLAYER_FIELDS["demand"]],
            }
            scored_players.append(scored_player)

    scored_players = sorted(
        scored_players, key=lambda player: player["raw_overall_score"], reverse=True
    )

    for i, player in enumerate(scored_players):
        player["raw_ranking"] = i
        player["overall_score"] = calculate_adjusted_score(
            player, all_players[player["id"]]
        )

    scored_players = sorted(
        scored_players, key=lambda player: player["overall_score"], reverse=True
    )

    position_players_by_100s = {
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
        9: 0,
        10: 0,
        11: 0,
    }

    rps_by_100s = {
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
        9: 0,
        10: 0,
        11: 0,
    }
    for i, player in enumerate(scored_players):
        is_position_player = player["position_player_score"] > player["pitcher_score"]
        is_rp = player["position"] == "RP" or player["position"] == "CL"
        dict_key = int(i / 100)
        if is_position_player:
            position_players_by_100s[dict_key] += 1
        if is_rp:
            rps_by_100s[dict_key] += 1

    with open(get_draft_class_eval_model_file(), "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=output_field_names)
        writer.writeheader()
        for i, player in enumerate(scored_players):
            player["ranking"] = i
            player["overall_score"] = round(player["overall_score"], 2)
            player["raw_overall_score"] = round(player["raw_overall_score"], 2)
            writer.writerow(player)
