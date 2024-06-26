import re
from sklearn.preprocessing import PolynomialFeatures
from sklearn import linear_model
from modifiers.base_rank_modifier import BaseRankModifier


def parse_demand(demand):
    is_thousands = demand[-1] == "k"
    is_millions = demand[-1] == "m"
    if not is_thousands and not is_millions:
        raise ValueError("Invalid Demand", demand)
    demand_as_number = int(re.sub("[^0-9]", "", demand))
    return demand_as_number * 1000 if is_thousands else demand_as_number * 100000


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

# used for 10-20
lt_20_min = 0.85
lt_20_ranking_demand_model = create_demand_modifier_model(
    [[8000000], [10000000]], [1, 0.85]
)

# used for 20 - 30
lt_30_min = 0.82
lt_30_ranking_demand_model = create_demand_modifier_model(
    [[7000000], [9000000]], [1, 0.82]
)

# used for 30 - 65
lt_65_min = 0.45
lt_65_ranking_demand_model = create_demand_modifier_model(
    [[2300000], [4300000], [5500000], [9000000]], [1, 0.9, 0.65, 0.45]
)


# used for 65 - 130
lt_130_ranking_demand_model = create_demand_modifier_model(
    [[900000], [1150000], [1650000], [2100000], [2700000]], [1, 0.9, 0.7, 0.6, 0.4]
)

lt_180_ranking_demand_model = create_demand_modifier_model(
    [[450000], [700000], [850000], [1000000], [2000000]], [1, 0.8, 0.8, 0.7, 0.4]
)

lt_280_ranking_demand_model = create_demand_modifier_model(
    [[430000], [500000], [700000], [1000000]], [1, 0.7, 0.7, 0.4]
)

gt_280_ranking_demand_model = create_demand_modifier_model(
    [[250000], [320000], [350000], [550000]], [0.95, 0.7, 0.5, 0.4]
)


class DraftDemandModifier(BaseRankModifier):
    @classmethod
    def calculate_player_modifier(cls, player, rank):
        modifier = 1
        if player.demand == "Slot":
            return modifier
        if player.demand == "Impossible":
            return base_modifier_min

        parsed_demand = parse_demand(player.demand)
        if rank < 10:
            return 1
        elif rank < 20:
            return run_demand_model(
                lt_20_ranking_demand_model, lt_20_min, parsed_demand
            )
        elif rank < 30:
            return run_demand_model(
                lt_30_ranking_demand_model, lt_30_min, parsed_demand
            )
        elif rank < 65:
            return run_demand_model(
                lt_65_ranking_demand_model, lt_65_min, parsed_demand
            )
        elif rank < 130:
            return run_demand_model(
                lt_130_ranking_demand_model, base_modifier_min, parsed_demand
            )
        elif rank < 180:
            return run_demand_model(
                lt_180_ranking_demand_model, base_modifier_min, parsed_demand
            )
        elif rank < 280:
            return run_demand_model(
                lt_280_ranking_demand_model, base_modifier_min, parsed_demand
            )
        return run_demand_model(
            gt_280_ranking_demand_model, base_modifier_min, parsed_demand
        )
