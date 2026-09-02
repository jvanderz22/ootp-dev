import pytest

from context import DraftClassContext
from load_draft_class import DatasetFormatError, create_dataset_from_upload
from models.game_players import GamePlayer, _int


def test_int_helper():
    assert _int("55") == 55
    assert _int(None) == 0
    assert _int("-") == 0
    assert _int("", None) is None
    assert _int("bogus", 7) == 7


def test_game_player_survives_missing_numeric_columns():
    p = GamePlayer({"ID": "1", "POS": "SP", "Name": "Test", "Age": ""})
    # missing rating columns must not raise
    assert p.age == 0
    assert p.stuff == 0
    assert p.contact == 0
    assert p.potential is None
    assert p.fastball is None  # pitch grades stay None so get_pitches() ignores them
    assert p.get_pitches() == []


def test_upload_rejects_file_without_required_columns(data_dir, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n")
    with pytest.raises(DatasetFormatError) as exc:
        create_dataset_from_upload("bad", str(bad), "draft_class")
    assert "ID" in str(exc.value) and "POS" in str(exc.value)


def test_upload_rejects_unparseable_html(data_dir, tmp_path):
    junk = tmp_path / "page.html"
    junk.write_text("<html><body><p>not a report</p></body></html>")
    with pytest.raises(DatasetFormatError):
        create_dataset_from_upload("junk", str(junk), "draft_class")
