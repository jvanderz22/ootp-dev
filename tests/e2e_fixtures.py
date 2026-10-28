"""Deterministic synthetic data for the end-to-end golden tests.

Everything here is generated from a seeded RNG so the golden outputs in
`tests/golden/` are reproducible without committing a real league export. The
value vocabularies (personality grades, G/F labels, velocity bands, ...) are the
ones a real OOTP scouting export / StatsPlus ratings CSV uses - the modifier maps
key on them, so an off-vocabulary value would KeyError the scorers.
"""
import csv
import io
import random

from statsplus_api import DraftPick
from tests.test_league_snapshot import PLAYERS_HEADER, RATINGS_HEADER

RATINGS = list(range(20, 85, 5))

FIRST_NAMES = [
    "Avery", "Blake", "Casey", "Dakota", "Emery", "Finley", "Gray", "Harper",
    "Indy", "Jordan", "Kai", "Logan", "Morgan", "Noel", "Oakley", "Parker",
    "Quinn", "Reese", "Sawyer", "Tatum",
]
LAST_NAMES = [
    "Abbott", "Barrow", "Calder", "Dunmore", "Ellery", "Fenwick", "Garrow",
    "Hollis", "Ingram", "Jessop", "Kettering", "Lowell", "Merritt", "Norcross",
    "Oakes", "Pembroke", "Quimby", "Radley", "Stanton", "Thorne",
]

# --------------------------------------------------------------- OOTP export
# The real header of an OOTP scouting export as converted by
# load_draft_class.create_csv (pandas index column + a blank column first).
OOTP_HEADER = [
    "", " ", "ID", "POS", "#", "Name", "ORG", "Lev", "DOB", "Age", "NAT", "HT",
    "WT", "B", "T", "OVR", "POT", "LEA", "LOY", "AD", "FIN", "WE", "INT", "Type",
    "Prone", "CON", "GAP", "POW", "EYE", "K's", "CON P", "GAP P", "POW P",
    "EYE P", "K P", "BBT", "GBT", "FBT", "STU", "MOV", "CONT", "STU P", "MOV P",
    "CONT P", "FB", "FBP", "CH", "CHP", "CB", "CBP", "SL", "SLP", "SI", "SIP",
    "SP", "SPP", "CT", "CTP", "FO", "FOP", "CC", "CCP", "SC", "SCP", "KC", "KCP",
    "KN", "KNP", "PIT", "G/F", "VELO", "VT", "Slot", "PT", "STM", "HLD", "C ABI",
    "C FRM", "C ARM", "IF RNG", "IF ERR", "IF ARM", "TDP", "OF RNG", "OF ERR",
    "OF ARM", "SPE", "SR", "STE", "RUN", "DEM", "DFA", "SctAcc",
]
# (current header, potential header) per pitch
OOTP_PITCHES = [
    ("CH", "CHP"), ("CB", "CBP"), ("SL", "SLP"), ("SI", "SIP"), ("SP", "SPP"),
    ("CT", "CTP"), ("FO", "FOP"), ("CC", "CCP"), ("SC", "SCP"), ("KC", "KCP"),
    ("KN", "KNP"),
]
POSITIONS = ["SP", "RP", "C", "CF", "2B", "SS", "3B", "RF", "1B", "LF", "CL"]
POSITION_WEIGHTS = [353, 169, 78, 77, 71, 56, 41, 37, 36, 33, 19]
VELOCITIES = [
    "80-83", "84-86", "85-87", "86-88", "87-89", "88-90", "89-91", "90-92",
    "91-93", "92-94", "93-95", "94-96", "95-97", "96-98",
]
DEMANDS = ["Slot"] * 8 + ["$650k", "$1.1m", "$3.2m", "$800k", "Impossible"]


def _grade(rng, lo, hi):
    """A rating on the 20-80 scale, a multiple of 5 within [lo, hi]."""
    return rng.choice([r for r in RATINGS if lo <= r <= hi])


def _current(rng, potential):
    return max(20, potential - rng.choice([0, 5, 10, 15, 20, 25]))


def _name(rng, i):
    return f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {rng.choice(LAST_NAMES)}"


def _personality(rng):
    return rng.choices(["N", "H", "L"], weights=[7, 2, 1.3])[0]


def make_draft_class_csv(n=160, seed=7) -> str:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        pos = rng.choices(POSITIONS, weights=POSITION_WEIGHTS)[0]
        pitcher = pos in ("SP", "RP", "CL")
        two_way = rng.random() < 0.04
        row = {h: "" for h in OOTP_HEADER}
        row.update({
            "": str(i), " ": "", "ID": str(90000 + i), "POS": pos,
            "#": str(rng.randint(1, 99)), "Name": _name(rng, i), "ORG": "-", "Lev": "-",
            "DOB": "05/11/2023", "Age": str(rng.choice([17, 18, 18, 19, 20, 21, 21, 22])),
            "NAT": "USA", "HT": "6' 2\"", "WT": "190 lbs",
            "B": rng.choices(["Right", "Left", "Switch"], weights=[6, 3, 1])[0],
            "T": rng.choices(["Right", "Left"], weights=[3, 1])[0],
            "OVR": str(_grade(rng, 20, 45)), "POT": str(_grade(rng, 35, 70)),
            "LEA": _personality(rng), "LOY": _personality(rng), "AD": _personality(rng),
            "FIN": _personality(rng), "WE": _personality(rng), "INT": _personality(rng),
            "Type": "Unknown",
            "Prone": rng.choices(["Normal", "Durable", "Fragile"], weights=[8, 1, 0.5])[0],
            "BBT": rng.choice(["Normal", "Normal", "Groundball", "Line Drive", "Flyball"]),
            "GBT": rng.choice(["Normal", "Normal", "Pull", "Spray", "Ex. Pull"]),
            "FBT": rng.choice(["Normal", "Pull", "Spray"]),
            "G/F": rng.choice(["NEU", "NEU", "FB", "EX FB", "GB", "EX GB"]),
            "Slot": rng.choice(["3/4", "3/4", "OTT", "SIDE"]), "PT": "Normal",
            "DEM": rng.choice(DEMANDS), "DFA": "-",
            "SctAcc": rng.choices(["Very High", "High"], weights=[9, 1])[0],
        })
        hit_lo, hit_hi = (20, 30) if pitcher and not two_way else (35, 75)
        for cur, pot in (("CON", "CON P"), ("GAP", "GAP P"), ("POW", "POW P"),
                         ("EYE", "EYE P"), ("K's", "K P")):
            p = _grade(rng, hit_lo, hit_hi)
            row[pot], row[cur] = str(p), str(_current(rng, p))
        pit_lo, pit_hi = (35, 75) if pitcher or two_way else (20, 30)
        for cur, pot in (("STU", "STU P"), ("MOV", "MOV P"), ("CONT", "CONT P")):
            p = _grade(rng, pit_lo, pit_hi)
            row[pot], row[cur] = str(p), str(_current(rng, p))
        for h in ("FB", "FBP") + tuple(h for pair in OOTP_PITCHES for h in pair):
            row[h] = "-"
        thrown = 0
        if pitcher or two_way:
            fb = _grade(rng, 40, 80)
            row["FBP"], row["FB"] = str(fb), str(_current(rng, fb))
            extra = rng.sample(OOTP_PITCHES[:6], rng.randint(1, 4))
            if rng.random() < 0.03:
                extra.append(("KN", "KNP"))
            for cur, pot in extra:
                p = _grade(rng, 30, 75)
                row[pot], row[cur] = str(p), str(_current(rng, p))
            thrown = 1 + len(extra)
        row["PIT"] = str(thrown)
        row["VT"] = rng.choice(VELOCITIES)
        row["VELO"] = VELOCITIES[max(0, VELOCITIES.index(row["VT"]) - 2)]
        row["STM"] = str(
            _grade(rng, 50, 75) if pos == "SP" else _grade(rng, 25, 45) if pitcher
            else _grade(rng, 20, 30)
        )
        row["HLD"] = str(_grade(rng, 20, 60))
        for h in ("C ABI", "C FRM", "C ARM"):
            row[h] = str(_grade(rng, 40, 70) if pos == "C" else _grade(rng, 20, 30))
        for h in ("IF RNG", "IF ERR", "IF ARM", "TDP", "OF RNG", "OF ERR", "OF ARM"):
            row[h] = str(_grade(rng, 20, 75))
        for h in ("SPE", "SR", "STE", "RUN"):
            row[h] = str(_grade(rng, 20, 80))
        rows.append(row)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=OOTP_HEADER)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def draft_picks(csv_text):
    """StatsPlus draft picks for the first dozen-odd players of the fixture class
    (every 7th id), across three teams, plus one id not in the class."""
    ids = [r["ID"] for r in csv.DictReader(io.StringIO(csv_text))]
    teams = ["Brewers", "Pirates", "Armadillos"]
    picks = []
    for n, pid in enumerate(ids[::7][:14]):
        picks.append(DraftPick(
            id=pid, name=f"Pick {n}", position="SP", round=str(n // 5 + 1),
            pick=str(n % 5 + 1), overall=str(n + 1), team=teams[n % 3],
        ))
    picks.append(DraftPick(
        id="99999", name="Not In Class", position="C", round="9", pick="1",
        overall="99", team="Brewers",
    ))
    return picks


# --------------------------------------------------------------- StatsPlus
# Four orgs: three in in-game league 100, one in league 200. Each has AAA / AA / A
# affiliates. Team 90 is a national team (top-level, no nickname).
ORGS = {"46": ("Milwaukee", "Brewers", 100), "52": ("Pittsburgh", "Pirates", 100),
        "60": ("Austin", "Armadillos", 100), "70": ("Boise", "Bison", 200)}
AFFILIATE_LEVELS = (("1", "2", "Triple"), ("2", "3", "Double"), ("3", "4", "Single"))
STATSPLUS_PITCHES = ["Snk", "Cutt", "Crv", "Sld", "Chg", "Splt"]
API_PITCHES = ["Fst", "Snk", "Cutt", "Crv", "Sld", "Chg", "Splt", "Frk", "CirChg",
               "Scr", "Kncrv", "Knbl"]
API_POSITIONS = ["SP", "SP", "RP", "RP", "C", "1B", "2B", "SS", "3B", "LF", "CF", "RF"]


def _teams_csv():
    lines = ["ID,Name,Nickname,Parent Team ID"]
    for oid, (city, nick, _lg) in ORGS.items():
        lines.append(f"{oid},{city},{nick},0")
        for prefix, _level, label in AFFILIATE_LEVELS:
            lines.append(f"{prefix}{oid},{city} {label},{nick} {label},{oid}")
    lines.append("90,Japan,,0")
    return "\n".join(lines) + "\n"


def _api_ratings_row(rng, pid, pos, **over):
    pitcher = pos in ("SP", "RP")
    row = {h: str(_grade(rng, 20, 60)) for h in RATINGS_HEADER}
    for h in RATINGS_HEADER:  # "0" = doesn't throw it, as the real API reports
        if (h[3:] if h.startswith("Pot") else h) in API_PITCHES:
            row[h] = "0"
    hit_lo, hit_hi = (20, 30) if pitcher else (35, 75)
    for cur in ("Cntct", "Gap", "Pow", "Eye", "Ks"):
        p = _grade(rng, hit_lo, hit_hi)
        row[f"Pot{cur}"], row[cur] = str(p), str(_current(rng, p))
    pit_lo, pit_hi = (35, 75) if pitcher else (20, 30)
    for cur in ("Stf", "Mov", "Ctrl"):
        p = _grade(rng, pit_lo, pit_hi)
        row[f"Pot{cur}"], row[cur] = str(p), str(_current(rng, p))
    if pitcher:
        fb = _grade(rng, 40, 80)
        row["PotFst"], row["Fst"] = str(fb), str(_current(rng, fb))
        for name in rng.sample(STATSPLUS_PITCHES, rng.randint(1, 4)):
            p = _grade(rng, 30, 75)
            row[f"Pot{name}"], row[name] = str(p), str(_current(rng, p))
    row.update({
        "ID": pid, "Name": _name(rng, int(pid)), "Pos": pos,
        "Age": str(rng.randint(18, 33)), "Height": "72",
        "Bats": rng.choice(["R", "R", "L", "S"]), "Throws": rng.choice(["R", "R", "L"]),
        "GBType": rng.choice(["0", "1", "2", "3"]), "FBType": rng.choice(["0", "1", "2"]),
        "Vel": rng.choice(VELOCITIES), "ArmSlot": "Normal",
        "GB": str(rng.randint(34, 78)),
        "Stm": str(_grade(rng, 50, 75) if pos == "SP" else _grade(rng, 25, 45)),
        "Prone": rng.choices(["Normal", "Durable", "Fragile"], weights=[8, 1, 0.5])[0],
        "Acc": rng.choice(["VH", "H", "A", "L"]),
        "Int": _personality(rng), "WrkEthic": _personality(rng),
        "Greed": _personality(rng), "Loy": _personality(rng), "Lead": _personality(rng),
        "Ovr": str(_grade(rng, 30, 65)), "Pot": str(_grade(rng, 40, 75)),
    })
    row["PotVel"] = row["Vel"]
    row.update(over)
    return row


def _api_players_row(pid, **over):
    row = {h: "0" for h in PLAYERS_HEADER}
    row.update({"ID": pid, "Age": "25", "bats": "1", "throws": "1"})
    row.update(over)
    return row


def _csv(header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def make_statsplus_csvs(seed=11):
    """(ratings_csv, players_csv, teams_csv) for a ~110-player fixture league that
    covers every snapshot-join branch: big leaguers, affiliates at each level, the
    international complex, an org-pool player, Rule 5 eligible / protected, both
    amateur pools, a released free agent and a national-team player."""
    rng = random.Random(seed)
    ratings, players = [], []
    next_id = [1000]

    def add(pos, rat_over, ply_over):
        pid = str(next_id[0])
        next_id[0] += 1
        ratings.append(_api_ratings_row(rng, pid, pos, **rat_over))
        players.append(_api_players_row(pid, **ply_over))

    for oid, (_city, _nick, game_league) in ORGS.items():
        lg = str(game_league)
        for _ in range(8):  # big leaguers on the 40-man
            add(rng.choice(API_POSITIONS),
                {"League": lg, "Team": oid, "Org": oid, "LgLvl": "1",
                 "Age": str(rng.randint(24, 33))},
                {"Team ID": oid, "Parent Team ID": oid, "Organization ID": oid,
                 "Level": "1", "League ID": lg, "is_on_secondary": "1",
                 "mlb_service_years": str(rng.randint(1, 8)),
                 "pro_service_years": str(rng.randint(4, 12)),
                 "years_protected_from_rule_5": "4"})
        add("SP",  # a rookie up with the big club (< 1 year MLS -> potential pool)
            {"League": lg, "Team": oid, "Org": oid, "LgLvl": "1", "Age": "23"},
            {"Team ID": oid, "Parent Team ID": oid, "Organization ID": oid,
             "Level": "1", "League ID": lg, "is_on_secondary": "1",
             "mlb_service_years": "0", "pro_service_years": "3",
             "years_protected_from_rule_5": "4"})
        for prefix, level, _label in AFFILIATE_LEVELS:
            team = f"{prefix}{oid}"
            for _ in range(5):
                protected = rng.choice(["4", "5"])
                add(rng.choice(API_POSITIONS),
                    {"League": lg, "Team": team, "Org": oid, "LgLvl": level,
                     "Age": str(rng.randint(19, 26))},
                    {"Team ID": team, "Parent Team ID": oid, "Organization ID": oid,
                     "Level": level, "League ID": lg,
                     "is_on_secondary": rng.choice(["0", "0", "1"]),
                     "pro_service_years": str(rng.randint(1, 5)),
                     "years_protected_from_rule_5": protected})
        add(rng.choice(API_POSITIONS),  # international complex
            {"League": f"-{lg}", "Team": oid, "Org": oid, "LgLvl": "1", "Age": "17"},
            {"Team ID": oid, "Parent Team ID": oid, "Organization ID": oid,
             "Level": "1", "League ID": f"-{lg}", "pro_service_years": "1",
             "years_protected_from_rule_5": "5"})
        add(rng.choice(API_POSITIONS),  # org pool: top-level team id below the majors
            {"League": lg, "Team": oid, "Org": oid, "LgLvl": "6", "Age": "19"},
            {"Team ID": oid, "Parent Team ID": oid, "Organization ID": oid,
             "Level": "6", "League ID": lg, "pro_service_years": "1",
             "years_protected_from_rule_5": "5"})

    for _ in range(4):  # amateur draft class
        add(rng.choice(API_POSITIONS),
            {"League": "0", "Team": "0", "Org": "0", "LgLvl": "0", "Age": "18"},
            {"Level": "0", "draft_eligible": "1"})
    for _ in range(3):  # international / undrafted amateur FA pool
        add(rng.choice(API_POSITIONS),
            {"League": "0", "Team": "0", "Org": "0", "LgLvl": "0", "Age": "16"},
            {"Level": "0"})
    add("RP",  # released pro free agent
        {"League": "0", "Team": "0", "Org": "0", "LgLvl": "0", "Age": "29"},
        {"Level": "0", "pro_service_years": "7", "last_team_id": "46",
         "mlb_service_years": "2"})
    add("SS",  # national-team player: org 90 is not a real org
        {"League": "0", "Team": "90", "Org": "90", "LgLvl": "0", "Age": "27"},
        {"Level": "0", "Team ID": "90", "Organization ID": "90",
         "pro_service_years": "6", "last_team_id": "90"})

    return _csv(RATINGS_HEADER, ratings), _csv(PLAYERS_HEADER, players), _teams_csv()
