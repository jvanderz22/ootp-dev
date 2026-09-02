from pathlib import Path

from context import DraftClassContext, default_base_dir


def test_base_dir_follows_data_dir_env(data_dir):
    assert default_base_dir() == Path(data_dir)
    ctx = DraftClassContext("abc")
    assert ctx.data_file == Path(data_dir) / "datasets" / "abc.csv"
    assert ctx.processed_dir == Path(data_dir) / "processed_classes" / "abc"
    assert ctx.eval_model_file("DraftClassRanker").parent.name == "DraftClassRanker"


def test_list_classes(data_dir):
    (data_dir / "datasets").mkdir()
    (data_dir / "datasets" / "b.csv").write_text("x")
    (data_dir / "datasets" / "a.csv").write_text("x")
    assert DraftClassContext.list_classes() == ["a", "b"]


def test_config_round_trip(data_dir):
    ctx = DraftClassContext("cfg")
    ctx.save_config({"ranking_method": "overall"})
    assert ctx.ranking_method == "overall"
