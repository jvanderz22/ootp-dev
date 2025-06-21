runtime_components = {}


def write_runtime_component(
    player_id: int, component_name: str, component_value: float
):
    if (runtime_components.get(player_id, None)) == None:
        runtime_components[player_id] = {}
    if component_value > 0:
        runtime_components[player_id][component_name] = round(component_value, 2)


def get_runtime_components(player_id):
    return runtime_components.get(player_id, None)
