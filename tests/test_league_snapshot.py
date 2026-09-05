"""Join + rename layer for the live league snapshot (see league_snapshot.py).

Fixtures mirror the real StatsPlus CSV headers captured from the `yfmlb` league;
rows are built from a default template so each test only spells out the columns
it cares about.
"""
import csv
import io

import pytest

import league_snapshot
from league_snapshot import (
    LeagueSnapshotContext,
    UNSOURCED_FIELDS,
    build_snapshot,
    gf_from_gb,
    join_rows,
    ranked_rows,
)
from models.game_players import PLAYER_FIELDS
from ranking_csv import RANKED_PLAYER_FIELDNAMES
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


def make_snapshot_csvs():
    """(ratings_csv, players_csv, teams_csv) for a two-player fixture league:
    id 100 = SP on Milwaukee (org 46), id 200 = RF on a Pittsburgh affiliate
    (roster team 168, parent org 52)."""
    pitcher = _ratings_row(
        ID="100", Name="Ace Hurler", Pos="SP", Team="46", Org="46", Bats="L", Throws="L",
        Acc="H", GB="35", GBType="1", FBType="2",
        Stf="60", Mov="55", Ctrl="50", PotStf="65", PotMov="60", PotCtrl="55",
        Fst="60", PotFst="65", Sld="55", PotSld="60", Chg="50", PotChg="55",
        Ovr="60", Pot="65",
    )
    hitter = _ratings_row(
        ID="200", Name="Big Bat", Pos="RF", Team="168", Org="52", LgLvl="3", Bats="S",
        Acc="A", GB="62", Cntct="55", Gap="50", Pow="65", Eye="45", Ks="50",
        PotCntct="60", PotPow="70", IFR="30", OFR="55", OFA="60", Speed="55",
        Steal="45", Run="50", Ovr="55", Pot="65",
    )
    players = [
        _players_row(ID="100", Level="1", **{"Team ID": "46", "Parent Team ID": "46", "Organization ID": "46"}),
        _players_row(ID="200", Level="4", **{"Team ID": "168", "Parent Team ID": "52", "Organization ID": "52"}),
        # note: no players row for a would-be id "300" -> join must tolerate it
    ]
    return (
        _csv(RATINGS_HEADER, [pitcher, hitter]),
        _csv(PLAYERS_HEADER, players),
        TEAMS_CSV,
    )


@pytest.fixture
def snapshot_csvs():
    return make_snapshot_csvs()


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

    # org resolved through the teams map (ratings Org is already the parent id)
    assert p["ORG"] == "Milwaukee"
    assert h["ORG"] == "Pittsburgh"

    # roster team / parent org ids kept for the web layer's grouping
    assert (p["snap_team_id"], p["snap_org_id"]) == ("46", "46")
    assert (h["snap_team_id"], h["snap_org_id"]) == ("168", "52")

    # phantom pitches (ratings "0") are blanked so they stay out of get_pitches()
    assert p["SI"] == "" and p["CT"] == "" and h["FB"] == ""


def test_org_name_walks_affiliate_to_parent():
    # an affiliate id in the ratings Org column still resolves to the top club
    ratings = _csv(RATINGS_HEADER, [_ratings_row(ID="9", Name="Farmhand", Pos="C", Org="168")])
    rows = join_rows(ratings, _csv(PLAYERS_HEADER, []), TEAMS_CSV)
    assert rows[0]["ORG"] == "Pittsburgh"
    assert rows[0]["snap_org_id"] == "168"


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


# --------------------------------------------------------------- ranking layer
@pytest.fixture
def built_ctx(tmp_path, snapshot_csvs):
    league_snapshot.evict_ranked_cache()
    ctx = LeagueSnapshotContext("yfmlb", base_dir=tmp_path)
    build_snapshot(ctx, *snapshot_csvs)
    yield ctx
    league_snapshot.evict_ranked_cache()


@pytest.mark.parametrize("method", ["overall", "potential"])
def test_ranked_rows_shape_and_order(built_ctx, method):
    rows = ranked_rows(built_ctx, method)

    assert [r["id"] for r in rows] == ["100", "200"] or [r["id"] for r in rows] == ["200", "100"]
    assert set(rows[0]) == set(RANKED_PLAYER_FIELDNAMES)
    # best-first: model_score descending, overall_ranking 0..n
    scores = [float(r["model_score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert [int(r["overall_ranking"]) for r in rows] == list(range(len(rows)))
    # snapshot has no demand source
    assert all(r["demand"] == "" for r in rows)


def test_ranked_rows_rejects_draft_class_method(built_ctx):
    with pytest.raises(ValueError):
        ranked_rows(built_ctx, "draft_class")


def test_ranked_rows_writes_and_reuses_disk_cache(built_ctx):
    ranker_name = get_ranker_for_method("overall").__class__.__name__
    out_file = built_ctx.ranked_players_file(ranker_name)

    ranked_rows(built_ctx, "overall")
    assert out_file.exists()
    first_mtime = out_file.stat().st_mtime

    league_snapshot.evict_ranked_cache()  # force past the process cache
    ranked_rows(built_ctx, "overall")
    assert out_file.stat().st_mtime == first_mtime  # not rewritten

    # a newer snapshot file invalidates the on-disk cache
    import os, time as _t
    later = _t.time() + 5
    os.utime(built_ctx.data_file, (later, later))
    league_snapshot.evict_ranked_cache()
    ranked_rows(built_ctx, "overall")
    assert out_file.stat().st_mtime > first_mtime


def test_ranked_rows_requires_a_snapshot(tmp_path):
    ctx = LeagueSnapshotContext("missing", base_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        ranked_rows(ctx, "overall")


def test_ranked_cache_evicts_least_recently_used(tmp_path, snapshot_csvs, monkeypatch):
    monkeypatch.setattr(league_snapshot, "_MAX_RANKED_ENTRIES", 2)
    league_snapshot.evict_ranked_cache()

    ctxs = []
    for i in range(3):
        ctx = LeagueSnapshotContext(f"lg{i}", base_dir=tmp_path)
        build_snapshot(ctx, *snapshot_csvs)
        ranked_rows(ctx, "overall")
        ctxs.append(ctx)

    keys = {k[0] for k in league_snapshot._ranked_cache}
    assert len(league_snapshot._ranked_cache) == 2
    assert str(ctxs[0].snapshot_dir) not in keys  # first one evicted
    assert str(ctxs[2].snapshot_dir) in keys
    league_snapshot.evict_ranked_cache()
