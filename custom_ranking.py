"""Per-class manual ranking order.

The model produces an order; the user may override it by dragging players around
in the UI. The override is stored as an explicit list of player ids in
processed_classes/<class>/custom_ranking.json. It is reconciled against the
current dataset on every read so re-uploads / re-scores never drop or duplicate
players:

* ids no longer in the dataset are removed,
* dataset players missing from the saved order are spliced back in at the
  position the model would give them.
"""
import json
import os
import time

from io_utils import atomic_write_json


def has_custom_order(ctx) -> bool:
    return os.path.exists(ctx.custom_ranking_file)


def load_order(ctx):
    if not has_custom_order(ctx):
        return None
    with open(ctx.custom_ranking_file) as f:
        data = json.load(f)
    order = data.get("order")
    return [str(pid) for pid in order] if isinstance(order, list) else None


def save_order(ctx, order, known_ids=None):
    order = [str(pid) for pid in order]
    if known_ids is not None:
        known = set(map(str, known_ids))
        seen = set()
        deduped = []
        for pid in order:
            if pid in known and pid not in seen:
                seen.add(pid)
                deduped.append(pid)
        order = deduped
    atomic_write_json(
        ctx.custom_ranking_file, {"order": order, "updated_at": time.time()}
    )
    return order


def clear_order(ctx) -> None:
    try:
        os.remove(ctx.custom_ranking_file)
    except FileNotFoundError:
        pass


def resolve_order(ctx, model_ranked_players):
    """Return `model_ranked_players` (list of dict rows with an ``id`` key)
    reordered by the saved custom order, if any."""
    saved = load_order(ctx)
    if not saved:
        return list(model_ranked_players)

    by_id = {str(row["id"]): row for row in model_ranked_players}
    model_index = {str(row["id"]): i for i, row in enumerate(model_ranked_players)}

    result = [pid for pid in saved if pid in by_id]
    placed = set(result)

    missing = sorted(
        (pid for pid in by_id if pid not in placed), key=lambda pid: model_index[pid]
    )
    for pid in missing:
        target = model_index[pid]
        insert_at = sum(1 for existing in result if model_index[existing] < target)
        result.insert(insert_at, pid)

    return [by_id[pid] for pid in result]
