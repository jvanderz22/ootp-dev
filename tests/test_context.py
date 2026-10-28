from pathlib import Path

from context import DraftClassContext, default_base_dir


def test_base_dir_follows_data_dir_env(data_dir):
    assert default_base_dir() == Path(data_dir)
    ctx = DraftClassContext("abc")
    assert ctx.data_file == Path(data_dir) / "datasets" / "abc.csv"
    assert ctx.processed_dir == Path(data_dir) / "processed_classes" / "abc"


def test_list_classes(data_dir):
    DraftClassContext("b").register()
    DraftClassContext("a").register()
    assert DraftClassContext.list_classes() == ["a", "b"]


def test_config_round_trip(data_dir):
    ctx = DraftClassContext("cfg")
    ctx.register()
    assert ctx.ranking_method == "draft_class"
    ctx.save_config({"ranking_method": "overall"})
    assert ctx.ranking_method == "overall"
    assert ctx.load_config()["print_method"] == "draft_prospects"


def test_register_again_bumps_versions_and_keeps_config(data_dir):
    import db

    ctx = DraftClassContext("re")
    ctx.register("potential")
    ctx.save_config({"print_method": "org_players"})
    before = db.query_one("SELECT data_version, revision FROM draft_classes WHERE name = 're'")
    ctx.register()  # a re-upload without a method keeps the stored one
    after = db.query_one("SELECT data_version, revision FROM draft_classes WHERE name = 're'")
    assert after["data_version"] == before["data_version"] + 1
    assert after["revision"] > before["revision"]
    assert ctx.load_config()["ranking_method"] == "potential"
    assert ctx.load_config()["print_method"] == "org_players"


def test_exists_needs_row_and_dataset(data_dir):
    ctx = DraftClassContext("ex")
    ctx.register()
    assert not ctx.exists()  # no dataset file yet
    ctx.ensure_dirs()
    ctx.data_file.write_text("ID,POS,Name\n")
    assert ctx.exists()
    ctx.unregister()
    assert not ctx.exists()
