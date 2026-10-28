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
import results_store
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
    "mlb_service_years", "pro_service_years", "pro_service_days", "last_team_id",
    "draft_eligible", "is_on_secondary", "years_protected_from_rule_5",
]

# `League ID` is negative for a player in the international complex (see
# `_is_intl_complex`); the default fixture rows use a positive placeholder.

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
    row.update({"Age": "25", "bats": "1", "throws": "1", "Level": "1", "League ID": "153"})
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
        # 100: big leaguer on the 40-man; 200: A-ball, off the 40-man, Rule 5 eligible
        _players_row(ID="100", Level="1", **{
            "Team ID": "46", "Parent Team ID": "46", "Organization ID": "46",
            "is_on_secondary": "1", "years_protected_from_rule_5": "4",
            "pro_service_years": "6",
        }),
        _players_row(ID="200", Level="4", **{
            "Team ID": "168", "Parent Team ID": "52", "Organization ID": "52",
            "years_protected_from_rule_5": "4", "pro_service_years": "3",
        }),
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


def _ctx_for(league_id):
    """A snapshot context for a freshly created league - a stored snapshot
    belongs to a league row."""
    from web import leagues

    assert leagues.create_league(league_id)["id"] == league_id
    return LeagueSnapshotContext(league_id)


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

    # level name comes from the /api/players/ integer code (4 -> A, per the
    # documented StatsPlus Level table)
    assert h["Lev"] == "A"
    assert p["Lev"] == "MLB"

    # org resolved through the teams map (ratings Org is already the parent id)
    assert p["ORG"] == "Milwaukee"
    assert h["ORG"] == "Pittsburgh"

    # roster team / parent org ids kept for the web layer's grouping
    assert (p["snap_team_id"], p["snap_org_id"]) == ("46", "46")
    assert (h["snap_team_id"], h["snap_org_id"]) == ("168", "52")

    # in-game league id kept so the web layer can scope views to one league
    assert p["snap_league_id"] == "153" and h["snap_league_id"] == "153"

    # phantom pitches (ratings "0") are blanked so they stay out of get_pitches()
    assert p["SI"] == "" and p["CT"] == "" and h["FB"] == ""


def test_org_name_walks_affiliate_to_parent():
    # an affiliate id in the ratings Org column still resolves to the top club
    ratings = _csv(RATINGS_HEADER, [_ratings_row(ID="9", Name="Farmhand", Pos="C", Org="168")])
    rows = join_rows(ratings, _csv(PLAYERS_HEADER, []), TEAMS_CSV)
    assert rows[0]["ORG"] == "Pittsburgh"
    assert rows[0]["snap_org_id"] == "168"


def test_international_complex_player_has_no_team():
    # a non-MLB player whose "Team" is a top-level club (id 46) is on the org's
    # complex / int'l pool, not the big-league roster - keep the org, drop the team
    ratings = _csv(RATINGS_HEADER, [
        _ratings_row(ID="7", Name="Teenage FA", Pos="SS", Team="46", Org="46", LgLvl="0"),
    ])
    players = _csv(PLAYERS_HEADER, [_players_row(ID="7", Level="0", **{"Team ID": "46"})])
    row = join_rows(ratings, players, TEAMS_CSV)[0]
    assert row["snap_org_id"] == "46"
    assert row["snap_team_id"] == ""
    # an actual MLB player on the same club id keeps the team
    ratings = _csv(RATINGS_HEADER, [_ratings_row(ID="8", Name="Vet", Pos="1B", Team="46", Org="46")])
    players = _csv(PLAYERS_HEADER, [_players_row(ID="8", Level="1", **{"Team ID": "46"})])
    assert join_rows(ratings, players, TEAMS_CSV)[0]["snap_team_id"] == "46"


def test_negative_league_id_marks_international_complex():
    # StatsPlus carries international-complex teenagers on the parent MLB club's
    # id at level 1, flagged only by a negative league id. They must not land on
    # the big-league roster, and the level reads "INT" not "MLB".
    ratings = _csv(RATINGS_HEADER, [
        _ratings_row(ID="11", Name="Intl Complex Kid", Pos="SS", Team="46", Org="46",
                     League="-153", LgLvl="1"),
    ])
    players = _csv(PLAYERS_HEADER, [
        _players_row(ID="11", Level="1", **{"Team ID": "46", "Parent Team ID": "46",
                                            "Organization ID": "46", "League ID": "-153"}),
    ])
    row = join_rows(ratings, players, TEAMS_CSV)[0]
    assert row["Lev"] == "INT"
    assert row["snap_org_id"] == "46"
    assert row["snap_team_id"] == ""
    # the negated league id is stored as its magnitude, so an int'l-complex kid
    # still counts toward his parent club's real league
    assert row["snap_league_id"] == "153"
    # not an amateur pool - he's signed, so he still gets ranked
    assert row["is_amateur"] == ""


def test_national_team_is_not_an_org():
    # OOTP lists Japan/China/etc. as nickname-less top-level teams; a player parked
    # on one is international-pool, not a member of that "club"
    teams = TEAMS_CSV + "765,China,,0\n"
    ratings = _csv(RATINGS_HEADER, [
        _ratings_row(ID="5", Name="Intl Amateur", Pos="SS", Team="765", Org="765", LgLvl="0"),
    ])
    players = _csv(PLAYERS_HEADER, [_players_row(ID="5", Level="0", **{"Team ID": "765"})])
    row = join_rows(ratings, players, teams)[0]
    assert row["snap_org_id"] == "" and row["ORG"] == ""
    assert row["snap_team_id"] == ""


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


def test_build_snapshot_writes_files(data_dir, snapshot_csvs):
    ctx = _ctx_for("yfmlb")
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
def built_ctx(data_dir, snapshot_csvs):
    ctx = _ctx_for("yfmlb")
    build_snapshot(ctx, *snapshot_csvs)
    return ctx


@pytest.mark.parametrize("method", ["overall", "potential"])
def test_ranked_rows_shape_and_order(built_ctx, method):
    rows = ranked_rows(built_ctx, method)

    assert [r["id"] for r in rows] == ["100", "200"] or [r["id"] for r in rows] == ["200", "100"]
    assert set(rows[0]) == set(results_store._RESULT_KEYS.values())
    # best-first: model_score descending
    scores = [float(r["model_score"]) for r in rows]
    assert scores == sorted(scores, reverse=True)
    # snapshot has no demand source
    assert all(r["demand"] == "" for r in rows)


def test_potential_ranking_excludes_established_mlb_players(data_dir, snapshot_csvs):
    """`mlb_service_years >= 1` drops a player from the potential ranking only -
    the overall ranking still scores everyone."""
    ratings, _players, teams = snapshot_csvs
    players = _csv(PLAYERS_HEADER, [
        _players_row(ID="100", Level="1", **{"mlb_service_years": "6"}),   # vet
        _players_row(ID="200", Level="4", **{"mlb_service_years": "0"}),   # rookie
    ])
    ctx = _ctx_for("svc")
    build_snapshot(ctx, ratings, players, teams)

    assert {r["id"] for r in ranked_rows(ctx, "overall")} == {"100", "200"}
    assert [r["id"] for r in ranked_rows(ctx, "potential")] == ["200"]


def test_amateur_pools_flagged_on_join(snapshot_csvs):
    ratings, _p, teams = snapshot_csvs
    players = _csv(PLAYERS_HEADER, [
        # draft class: draft_eligible flag, level 0, no history
        _players_row(ID="100", Level="0", **{"draft_eligible": "1", "last_team_id": "0"}),
        # int'l / undrafted amateur FA: not draft eligible but never signed
        _players_row(ID="200", Level="0", **{
            "draft_eligible": "0", "pro_service_years": "0",
            "pro_service_days": "0", "last_team_id": "0",
        }),
    ])
    rows = {r["ID"]: r for r in join_rows(ratings, players, teams)}
    assert rows["100"]["is_amateur"] == "1"
    assert rows["200"]["is_amateur"] == "1"


def test_released_free_agent_is_not_flagged_amateur(snapshot_csvs):
    ratings, _p, teams = snapshot_csvs
    players = _csv(PLAYERS_HEADER, [
        # level 0 but a former pro (service time + a last team) -> a real FA
        _players_row(ID="100", Level="0", **{
            "draft_eligible": "0", "pro_service_years": "8", "last_team_id": "46",
        }),
    ])
    row = join_rows(ratings, players, teams)[0]
    assert row["is_amateur"] == ""


def test_rankings_exclude_amateur_pools(data_dir, snapshot_csvs):
    """Draft-class and amateur-FA players are dropped from BOTH rankings."""
    ratings, _p, teams = snapshot_csvs
    players = _csv(PLAYERS_HEADER, [
        _players_row(ID="100", Level="0", **{"draft_eligible": "1"}),          # draft class
        _players_row(ID="200", Level="4", **{"last_team_id": "168"}),          # real prospect
    ])
    ctx = _ctx_for("amateurs")
    build_snapshot(ctx, ratings, players, teams)

    for method in ("overall", "potential"):
        assert [r["id"] for r in ranked_rows(ctx, method)] == ["200"]


def test_player_count_excludes_amateurs(data_dir, snapshot_csvs):
    ratings, _p, teams = snapshot_csvs
    players = _csv(PLAYERS_HEADER, [
        _players_row(ID="100", Level="0", **{"draft_eligible": "1"}),   # amateur
        _players_row(ID="200", Level="4", **{"last_team_id": "168"}),   # real player
    ])
    ctx = _ctx_for("count")
    build_snapshot(ctx, ratings, players, teams)

    meta = ctx.load_meta()
    assert meta["player_count"] == 1        # the amateur doesn't count
    assert meta["total_row_count"] == 2     # raw snapshot size still recorded


@pytest.mark.parametrize(
    "fields, org_id, expected",
    [
        # signed at 19+ (window 4): eligible in his 4th Rule 5 draft, i.e. with 3
        # pro seasons credited - the season in progress isn't counted yet
        ({"years_protected_from_rule_5": "4", "pro_service_years": "3"}, "52", True),
        ({"years_protected_from_rule_5": "4", "pro_service_years": "2"}, "52", False),
        # signed at 18 or younger (window 5): one more year of protection
        ({"years_protected_from_rule_5": "5", "pro_service_years": "3"}, "52", False),
        ({"years_protected_from_rule_5": "5", "pro_service_years": "4"}, "52", True),
        # long past the window
        ({"years_protected_from_rule_5": "4", "pro_service_years": "9"}, "52", True),
        # protected by the 40-man roster
        ({"years_protected_from_rule_5": "4", "pro_service_years": "9",
          "is_on_secondary": "1"}, "52", False),
        # not in an org (free agent) -> nothing to be drafted from
        ({"years_protected_from_rule_5": "4", "pro_service_years": "9"}, "", False),
        # blank fields (no players row data) -> not eligible
        ({"years_protected_from_rule_5": "", "pro_service_years": ""}, "52", False),
    ],
)
def test_is_rule5_eligible(fields, org_id, expected):
    ply = {"is_on_secondary": "0", **fields}
    assert league_snapshot._is_rule5_eligible(ply, org_id) is expected


def test_rule5_eligibility_written_on_join(snapshot_csvs):
    rows = {r["ID"]: r for r in join_rows(*snapshot_csvs)}
    assert rows["100"]["rule_5_eligible"] == ""   # on the 40-man
    assert rows["200"]["rule_5_eligible"] == "1"


def test_ranked_rows_rejects_draft_class_method(built_ctx):
    with pytest.raises(ValueError):
        ranked_rows(built_ctx, "draft_class")


def test_ranked_rows_reuses_the_stored_run_until_the_snapshot_changes(
    built_ctx, snapshot_csvs, monkeypatch
):
    first = ranked_rows(built_ctx, "overall")
    run = results_store.run_info(results_store.LEAGUE, "yfmlb", "overall")
    assert run["source_version"] == league_snapshot.snapshot_version(built_ctx)
    assert league_snapshot.ranked_method_is_fresh(built_ctx, "overall")

    def no_rescore(*a, **k):
        raise AssertionError("re-scored a current ranking")

    with monkeypatch.context() as m:
        m.setattr(league_snapshot, "_score", no_rescore)
        assert ranked_rows(built_ctx, "overall") == first

    # a refreshed snapshot (new version) makes the stored run stale
    build_snapshot(built_ctx, *snapshot_csvs)
    assert not league_snapshot.ranked_method_is_fresh(built_ctx, "overall")
    ranked_rows(built_ctx, "overall")
    rescored = results_store.run_info(results_store.LEAGUE, "yfmlb", "overall")
    assert rescored["source_version"] == run["source_version"] + 1


def test_ranked_rows_requires_a_snapshot(data_dir):
    ctx = _ctx_for("missing")
    with pytest.raises(FileNotFoundError):
        ranked_rows(ctx, "overall")


# ------------------------------------------------------------ platoon splits
def _split_csvs():
    """One hitter who mashes lefties (+15 on every vs-L tool) and is weak vs
    righties (-10); the fixture pitcher's splits are left at the default."""
    ratings, players, teams = make_snapshot_csvs()
    rows = list(csv.DictReader(io.StringIO(ratings)))
    hitter = next(r for r in rows if r["ID"] == "200")
    for col in ("Cntct", "Gap", "Pow", "Eye", "Ks"):
        hitter[f"{col}_L"] = str(int(hitter[col]) + 15)
        hitter[f"{col}_R"] = str(int(hitter[col]) - 10)
    return _csv(RATINGS_HEADER, rows), players, teams


def test_split_ratings_mapped():
    rows = {r["ID"]: r for r in join_rows(*_split_csvs())}
    assert rows["200"]["CON vL"] == "70" and rows["200"]["CON vR"] == "45"
    assert rows["200"]["K's vL"] == "65"
    assert rows["100"]["STU vL"] == "40" and rows["100"]["CONT vR"] == "40"


def test_player_splits_scores_each_side(data_dir):
    from web import service

    ctx = _ctx_for("yfmlb")
    build_snapshot(ctx, *_split_csvs())
    s = service.player_splits({"league_id": "yfmlb"}, "200")

    assert s["vs_l"]["contact"] == 70 and s["vs_r"]["contact"] == 45
    assert s["combined"]["contact"] == 55
    assert s["vs_l"]["batter_score"] > s["combined"]["batter_score"] > s["vs_r"]["batter_score"]


def test_player_splits_unavailable(data_dir):
    from web import service

    ctx = _ctx_for("yfmlb")
    ratings, players, teams = make_snapshot_csvs()
    # a snapshot written before splits were kept has no split columns at all
    rows = list(csv.DictReader(io.StringIO(ratings)))
    header = [h for h in RATINGS_HEADER if not h.endswith(("_L", "_R"))]
    build_snapshot(ctx, _csv(header, [{h: r[h] for h in header} for r in rows]), players, teams)

    assert service.player_splits({"league_id": "yfmlb"}, "200") is None
    assert service.player_splits({"league_id": "yfmlb"}, "999") is None
    assert service.player_splits({"class_name": "anything"}, "200") is None
