import re
from sklearn import linear_model
from modifiers.base_rank_modifier import BaseRankModifier

DEMAND_INFLATION_MODIFIER = 1.06


def parse_demand(demand):
    is_thousands = demand[-1] == "k"
    is_millions = demand[-1] == "m"
    if not is_thousands and not is_millions:
        raise ValueError("Invalid Demand", demand)
    demand_as_number = int(re.sub("[^0-9]", "", demand))
    return demand_as_number * 1000 if is_thousands else demand_as_number * 100000


base_modifier_min = 0.4


def create_demand_modifier_model(x, y, min_value=base_modifier_min):
    x_splits = [
        [[x[i] * DEMAND_INFLATION_MODIFIER], [x[i + 1] * DEMAND_INFLATION_MODIFIER]]
        for (i, _v) in enumerate(x[:-1])
    ]
    y_splits = [[y[i], y[i + 1]] for (i, _v) in enumerate(y[:-1])]
    models = []
    for i, split in enumerate(x_splits):
        reg = linear_model.LinearRegression()
        reg.fit(split, y_splits[i])
        models.append(reg)

    return {"models": models, "x_range": x_splits, "min_value": min_value}


def run_demand_model(model, value):
    matching_model_idx = next(
        filter(
            lambda i: model["x_range"][i][0][0] <= value
            and model["x_range"][i][1][0] >= value,
            range(len(model["x_range"])),
        ),
        None,
    )
    if matching_model_idx is None:
        if value < model["x_range"][0][0][0]:
            return 1
        else:
            return model["min_value"]
    matching_model = model["models"][matching_model_idx]

    max_val = max(matching_model.predict([[value]])[0], model["min_value"])
    return min(max_val, 1)


# used for 10-20
lt_20_min = 0.85
lt_20_ranking_demand_model = create_demand_modifier_model(
    [8000000, 10000000], [1, 0.85], lt_20_min
)

# used for 20 - 30
lt_30_min = 0.82
lt_30_ranking_demand_model = create_demand_modifier_model(
    [7000000, 9000000], [1, 0.82], lt_30_min
)

# used for 30 - 65
lt_65_min = 0.45
lt_65_ranking_demand_model = create_demand_modifier_model(
    [2300000, 4300000, 5500000, 9000000], [1, 0.9, 0.65, 0.45], lt_65_min
)

# used for 65-90
lt_90_ranking_demand_model = create_demand_modifier_model(
    [1_400_000, 2_500_000, 3_450_000, 4_400_000, 6_600_000], [1, 0.9, 0.7, 0.6, 0.4]
)

# used for 90 - 130
lt_130_ranking_demand_model = create_demand_modifier_model(
    [900000, 1150000, 1650000, 2100000, 2700000], [1, 0.9, 0.7, 0.6, 0.4]
)

lt_180_ranking_demand_model = create_demand_modifier_model(
    [450000, 700000, 850000, 1000000, 2000000], [1, 0.8, 0.8, 0.7, 0.4]
)

lt_280_ranking_demand_model = create_demand_modifier_model(
    [430000, 500000, 700000, 1000000], [1, 0.7, 0.7, 0.4]
)

gt_280_ranking_demand_model = create_demand_modifier_model(
    [250000, 320000, 350000, 550000], [0.95, 0.7, 0.5, 0.4]
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
            return run_demand_model(lt_20_ranking_demand_model, parsed_demand)
        elif rank < 30:
            return run_demand_model(lt_30_ranking_demand_model, parsed_demand)
        elif rank < 65:
            return run_demand_model(
                lt_65_ranking_demand_model,
                parsed_demand,
            )
        elif rank < 90:
            return run_demand_model(lt_90_ranking_demand_model, parsed_demand)
        elif rank < 130:
            return run_demand_model(lt_130_ranking_demand_model, parsed_demand)
        elif rank < 180:
            return run_demand_model(lt_180_ranking_demand_model, parsed_demand)
        elif rank < 280:
            return run_demand_model(lt_280_ranking_demand_model, parsed_demand)
        return run_demand_model(gt_280_ranking_demand_model, parsed_demand)
