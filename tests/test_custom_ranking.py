from context import DraftClassContext
from custom_ranking import clear_order, has_custom_order, resolve_order, save_order


def rows(ids):
    return [{"id": i} for i in ids]


def test_no_file_is_identity(data_dir):
    ctx = DraftClassContext("c")
    ctx.processed_dir.mkdir(parents=True)
    model = rows(["1", "2", "3"])
    assert [r["id"] for r in resolve_order(ctx, model)] == ["1", "2", "3"]


def test_saved_reorder_is_applied(data_dir):
    ctx = DraftClassContext("c")
    ctx.processed_dir.mkdir(parents=True)
    model = rows(["1", "2", "3", "4"])
    save_order(ctx, ["3", "1", "2", "4"], known_ids=["1", "2", "3", "4"])
    assert [r["id"] for r in resolve_order(ctx, model)] == ["3", "1", "2", "4"]
    assert has_custom_order(ctx)


def test_removed_id_is_dropped(data_dir):
    ctx = DraftClassContext("c")
    ctx.processed_dir.mkdir(parents=True)
    save_order(ctx, ["3", "1", "2"], known_ids=["1", "2", "3"])
    model = rows(["1", "2"])  # id 3 no longer in the dataset
    assert [r["id"] for r in resolve_order(ctx, model)] == ["1", "2"]


def test_new_id_is_spliced_at_model_position(data_dir):
    ctx = DraftClassContext("c")
    ctx.processed_dir.mkdir(parents=True)
    save_order(ctx, ["3", "1"], known_ids=["1", "3"])
    # model now also has "2", which the model ranks between "1" and "3"
    model = rows(["1", "2", "3"])
    resolved = [r["id"] for r in resolve_order(ctx, model)]
    assert set(resolved) == {"1", "2", "3"} and len(resolved) == 3
    # "2" is spliced in ahead of the one already-placed player the model ranks
    # below it ("1"), preserving the user's "3 before 1" override.
    assert resolved == ["3", "2", "1"]


def test_clear(data_dir):
    ctx = DraftClassContext("c")
    ctx.processed_dir.mkdir(parents=True)
    save_order(ctx, ["1"], known_ids=["1"])
    clear_order(ctx)
    assert not has_custom_order(ctx)
