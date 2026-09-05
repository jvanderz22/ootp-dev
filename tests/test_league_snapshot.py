"""Join + rename layer for the live league snapshot (see league_snapshot.py).

Fixtures mirror the real StatsPlus CSV headers captured from the `yfmlb` league;
rows are built from a default template so each test only spells out the columns
it cares about.
"""
import csv
import io

import pytest

from league_snapshot import (
    LeagueSnapshotContext,
    UNSOURCED_FIELDS,
    build_snapshot,
    gf_from_gb,
    join_rows,
)
from models.game_players import PLAYER_FIELDS
from rankers.get_ranker import get_ranker_for_method

# --- real captured headers --------------------------------------------------
RATINGS_HEADER = (
    "ID,Name,Pos,League,Team,Org,LgLvl,Age,Height,Bats,Throws,Cntct,Gap,Pow,Eye,Ks,"
    "BABIP,Cntct_R,Gap_R,Pow_R,Eye_R,Ks_R,BABIP_R,Cntct_L,Gap_L,Pow_L,Eye_L,Ks_L,"
    "BABIP_L,PotCntct,PotGap,PotPow,PotEye,PotKs,PotBABIP,IFR,IFE,IFA,TDP,OFR,OFE,"
    "OFA,CBlk,CArm,CFrm,P,C,1B,2B,3B,SS,LF,CF,RF,PotP,PotC,Pot1B,Pot2B,Pot3B,PotSS,"
    "PotLF,PotCF,PotRF,Speed,StlRt,Steal,Run,SacBunt,BuntHit,GBType,FBType,Stf,Mov,"
    "HRA,PBABIP,Ctrl,Stf_R,Mov_R,HRA_R,PBABIP_R,Ctrl_R,Stf_L,Mov_L,HRA_L,PBABIP_L,"
    "Ctrl_L,PotStf,PotMov,PotHRA,PotPBABIP,PotCtrl,Vel,PotVel,ArmSlot,GB,Stm,Hold,"
    "Fst,Snk,Cutt,Crv,Sld,Chg,Splt,Frk,CirChg,Scr,Kncrv,Knbl,PotFst,PotSnk,PotCutt,"
    "PotCrv,PotSld,PotChg,PotSplt,PotFrk,PotCirChg,PotScr,PotKncrv,PotKnbl,Int,"
    "WrkEthic,Greed,Loy,Lead,Prone,Acc,Ovr,Pot"
).split(",")

PLAYERS_HEADER = [
    "ID", "First Name", "Last Name", "Team ID", "Parent Team ID", "Level", "Pos",
    "Role", "Age", "Organization ID", "League ID", "bats", "throws",
]

TEAMS_CSV = (
    "ID,Name,Nickname,Parent Team ID\n"
    "46,Milwaukee,Brewers,0\n"
    "168,Indianapolis,Indians,52\n"
    "52,Pittsburgh,Pirates,0\n"
)


def _ratings_row(**over):
    row = {h: "40" for h in RATINGS_HEADER}
    row.update({h: "0" for h in RATINGS_HEADER if h.startswith(("Fst", "Snk", "Cutt",
               "Crv", "Sld", "Chg", "Splt", "Frk", "CirChg", "Scr", "Kncrv", "Knbl",
               "PotFst", "PotSnk", "PotCutt", "PotCrv", "PotSld", "PotChg", "PotSplt",
               "PotFrk", "PotCirChg", "PotScr", "PotKncrv", "PotKnbl"))})
    row.update({
        "League": "153", "Team": "46", "Org": "46", "LgLvl": "1", "Age": "25",
        "Height": "72", "Bats": "R", "Throws": "R", "GBType": "0", "FBType": "0",
        "Vel": "92-94", "PotVel": "92-94", "ArmSlot": "Normal", "GB": "50",
        "Stm": "45", "Hold": "40", "Prone": "Normal", "Acc": "VH",
        "Int": "N", "WrkEthic": "N", "Greed": "N", "Loy": "N", "Lead": "N",
        "Ovr": "45", "Pot": "50",
    })
    row.update(over)
    return row


def _players_row(**over):
    row = {h: "0" for h in PLAYERS_HEADER}
    row.update({"Age": "25", "bats": "1", "throws": "1", "Level": "1"})
    row.update(over)
    return row


def _csv(header, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


@pytest.fixture
def snapshot_csvs():
    pitcher = _ratings_row(
        ID="100", Name="Ace Hurler", Pos="SP", Org="46", Bats="L", Throws="L",
        Acc="H", GB="35", GBType="1", FBType="2",
        Stf="60", Mov="55", Ctrl="50", PotStf="65", PotMov="60", PotCtrl="55",
        Fst="60", PotFst="65", Sld="55", PotSld="60", Chg="50", PotChg="55",
        Ovr="60", Pot="65",
    )
    hitter = _ratings_row(
        ID="200", Name="Big Bat", Pos="RF", Org="168", LgLvl="3", Bats="S",
        Acc="A", GB="62", Cntct="55", Gap="50", Pow="65", Eye="45", Ks="50",
        PotCntct="60", PotPow="70", IFR="30", OFR="55", OFA="60", Speed="55",
        Steal="45", Run="50", Ovr="55", Pot="65",
    )
    players = [
        _players_row(ID="100", Level="1", **{"Parent Team ID": "46", "Organization ID": "46"}),
        _players_row(ID="200", Level="4", **{"Parent Team ID": "52", "Organization ID": "52"}),
        # note: no players row for a would-be id "300" -> join must tolerate it
    ]
    return (
        _csv(RATINGS_HEADER, [pitcher, hitter]),
        _csv(PLAYERS_HEADER, players),
        TEAMS_CSV,
    )


def test_header_covers_player_fields(snapshot_csvs):
    rows = join_rows(*snapshot_csvs)
    header = set(rows[0])
    needed = set(PLAYER_FIELDS.values()) - UNSOURCED_FIELDS
    assert needed <= header
    # the three that genuinely have no API source are present but always blank
    for r in rows:
        for f in UNSOURCED_FIELDS:
            assert r[f] == ""


def test_rename_and_value_maps(snapshot_csvs):
    rows = {r["ID"]: r for r in join_rows(*snapshot_csvs)}
    p, h = rows["100"], rows["200"]

    assert p["POS"] == "SP" and p["Name"] == "Ace Hurler"
    assert (p["STU"], p["MOV"], p["CONT"]) == ("60", "55", "50")
    assert (p["STU P"], p["MOV P"], p["CONT P"]) == ("65", "60", "55")
    assert (p["FB"], p["FBP"], p["SL"], p["CH"]) == ("60", "65", "55", "50")
    assert (p["OVR"], p["POT"]) == ("60", "65")

    # handedness + scouting-accuracy codes -> the words the modifiers key on
    assert p["B"] == "Left" and p["T"] == "Left"
    assert h["B"] == "Switch"
    assert p["SctAcc"] == "High" and h["SctAcc"] == "Average"

    # batting block for the hitter
    assert (h["CON"], h["POW"], h["EYE"]) == ("55", "65", "45")
    assert (h["CON P"], h["POW P"]) == ("60", "70")
    assert (h["OF RNG"], h["OF ARM"]) == ("55", "60")

    # level name comes from the /api/players/ integer code (4 -> A+)
    assert h["Lev"] == "A+"
    assert p["Lev"] == "MLB"

    # org resolved through the teams map: 46 -> Milwaukee, 168's parent 52 uses
    # the ratings Org (already the parent) -> Pittsburgh
    assert p["ORG"] == "Milwaukee"
    assert h["ORG"] == "Pittsburgh"

    # phantom pitches (ratings "0") are blanked so they stay out of get_pitches()
    assert p["SI"] == "" and p["CT"] == "" and h["FB"] == ""


def test_gf_bucketing():
    assert gf_from_gb("20") == "EX FB"
    assert gf_from_gb("45") == "FB"
    assert gf_from_gb("50") == "NEU"
    assert gf_from_gb("58") == "GB"
    assert gf_from_gb("75") == "EX GB"
    assert gf_from_gb("") == "NEU"
    assert gf_from_gb(None) == "NEU"


def test_join_tolerates_missing_players_row():
    ratings = _csv(RATINGS_HEADER, [
        _ratings_row(ID="300", Name="Orphan", Pos="C"),
    ])
    players = _csv(PLAYERS_HEADER, [])  # header only
    rows = join_rows(ratings, players, TEAMS_CSV)
    assert len(rows) == 1
    assert rows[0]["Name"] == "Orphan"
    assert rows[0]["Lev"] == "MLB"  # fell back to ratings LgLvl "1"


@pytest.mark.parametrize("method", ["overall", "potential"])
def test_rankers_score_snapshot_rows(snapshot_csvs, method):
    from models.game_players import GamePlayer

    rows = join_rows(*snapshot_csvs)
    ranker = get_ranker_for_method(method)
    scores = ranker.rank([GamePlayer(r) for r in rows])
    assert len(scores) == len(rows)
    assert all(s.overall_score is not None for s in scores)


def test_build_snapshot_writes_files(tmp_path, snapshot_csvs):
    ctx = LeagueSnapshotContext("yfmlb", base_dir=tmp_path)
    build_snapshot(ctx, *snapshot_csvs)

    assert ctx.data_file.exists()
    with open(ctx.data_file, newline="") as f:
        written = list(csv.DictReader(f))
    assert [r["ID"] for r in written] == ["100", "200"]

    meta = ctx.load_meta()
    assert meta["league_id"] == "yfmlb"
    assert meta["player_count"] == 2
    assert "fetched_at" in meta
    assert ctx.teams_file.exists()
