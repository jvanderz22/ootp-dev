"""Live league snapshot: the whole player pool pulled from StatsPlus, ranked.

Parallel to the draft-class flow (`context.py` / `pipeline.py`) but covering every
player in a league instead of one hand-uploaded draft class. Three StatsPlus
endpoints (see `statsplus_api.py`) are joined on the OOTP player `ID` and their
columns renamed to the OOTP scouting-export headers `models/game_players.py`'s
`PLAYER_FIELDS` expects, so the existing rankers score a snapshot row exactly as
they score a draft-class row.

    ratings CSV  (GET /api/ratings/, async)  -> the scouting grid
    players CSV  (GET /api/players/)         -> level, org / parent-team ids
    teams CSV    (GET /api/teams/)           -> id -> name for org resolution

`DEM` (demand), `Sign` (signability) and `AD` (adaptability) have no API source
and are left blank: `rankers/overall_ranker.py` and
`rankers/overall_potential_ranker.py` - the only two methods the league view
offers - reference none of them (only `DraftClassRanker` does).

VALUE-MAPPING CAVEATS (a few ratings columns are codes, not the export's words -
verify against a real in-game scouting report before trusting them):
  * ``G/F``  is bucketed from the numeric ``GB`` column via ``GF_BUCKETS`` -
    thresholds are a first guess.
  * ``GBT`` / ``FBT`` come from the ``GBType`` / ``FBType`` integer codes; the
    Pull vs Spray ordering is unconfirmed.
  * ``Lev`` names come from ``LEVEL_NAMES`` keyed on the integer level code.
  * ``C ABI`` is taken from ``CBlk`` (catcher blocking).
"""
import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
import results_store
from context import default_base_dir
from models.game_players import (
    PLAYER_FIELDS, SPLIT_HEADERS, SPLIT_SIDES, GamePlayer, split_header,
)
from rankers.base_ranker import DEFAULT_BATCH_SIZE
from rankers.get_ranker import get_ranker_for_method
from statsplus_api import (
    StatsPlusError,
    fetch_league_date,
    fetch_players,
    fetch_ratings,
    fetch_teams,
)

# The league view only ever offers these two ranking methods (see the plan / the
# `statsplus-api` memory): neither reads `demand` / `adaptability`, the fields the
# API can't supply.
LEAGUE_RANKING_METHODS = ("overall", "potential")

# Every OOTP header the pipeline can read. We write them all; the ones with no
# API source (DEM / Sign / AD and any unmapped extra) stay blank.
OUTPUT_FIELDNAMES = list(dict.fromkeys(PLAYER_FIELDS.values()))
UNSOURCED_FIELDS = {"DEM", "Sign", "AD"}

# Non-OOTP bookkeeping columns kept alongside the scouting grid, all sourced from
# `/api/players/` and all invisible to the rankers (`GamePlayer` ignores columns
# it doesn't know):
#   snap_team_id / snap_org_id  - the web layer groups a snapshot by these
#   snap_league_id              - the OOTP in-game league the player's team plays
#                                 in (abs value; StatsPlus negates it for the
#                                 international complex). Lets the web layer scope
#                                 the by-org / farm-system views to one in-game
#                                 league when a StatsPlus export spans several
#                                 (see `web/leagues.py` `game_league_ids`).
#   mlb_service_years           - gates the potential ranking to < 1 year MLS
#   is_amateur ("1" / "")       - the amateur draft class + international /
#                                 undrafted amateur FA pool; excluded from BOTH
#                                 rankings (see `_is_amateur`)
#   rule_5_eligible ("1" / "")  - exposed in the upcoming Rule 5 draft (see
#                                 `_is_rule5_eligible`)
SNAPSHOT_META_FIELDS = [
    "snap_team_id", "snap_org_id", "snap_league_id", "mlb_service_years",
    "is_amateur", "rule_5_eligible",
]
SNAPSHOT_FIELDNAMES = OUTPUT_FIELDNAMES + SPLIT_HEADERS + SNAPSHOT_META_FIELDS


# --------------------------------------------------------------- column mapping
# ratings CSV column -> OOTP scouting-export header. Straight renames only;
# anything needing a value transform is handled in `_map_row`.
RATINGS_COLUMN_MAP = {
    "ID": "ID",
    "Name": "Name",
    "Pos": "POS",
    "Age": "Age",
    # batting - current
    "Cntct": "CON", "Gap": "GAP", "Pow": "POW", "Eye": "EYE", "Ks": "K's",
    # batting - potential
    "PotCntct": "CON P", "PotGap": "GAP P", "PotPow": "POW P",
    "PotEye": "EYE P", "PotKs": "K P",
    # infield / outfield / catcher defense
    "IFR": "IF RNG", "IFE": "IF ERR", "IFA": "IF ARM", "TDP": "TDP",
    "OFR": "OF RNG", "OFE": "OF ERR", "OFA": "OF ARM",
    "CBlk": "C ABI", "CArm": "C ARM", "CFrm": "C FRM",
    # speed / baserunning
    "Speed": "SPE", "Steal": "STE", "Run": "RUN",
    # pitching - current / potential
    "Stf": "STU", "Mov": "MOV", "Ctrl": "CONT",
    "PotStf": "STU P", "PotMov": "MOV P", "PotCtrl": "CONT P",
    "Stm": "STM", "Vel": "VT", "ArmSlot": "Slot",
    # individual pitches - current
    "Fst": "FB", "Snk": "SI", "Cutt": "CT", "Crv": "CB", "Sld": "SL", "Chg": "CH",
    "Splt": "SP", "Frk": "FO", "CirChg": "CC", "Scr": "SC", "Kncrv": "KC", "Knbl": "KN",
    # individual pitches - potential
    "PotFst": "FBP", "PotSnk": "SIP", "PotCutt": "CTP", "PotCrv": "CBP",
    "PotSld": "SLP", "PotChg": "CHP", "PotSplt": "SPP", "PotFrk": "FOP",
    "PotCirChg": "CCP", "PotScr": "SCP", "PotKncrv": "KCP", "PotKnbl": "KNP",
    # makeup / overall
    "Int": "INT", "WrkEthic": "WE", "Greed": "FIN", "Loy": "LOY", "Lead": "LEA",
    "Prone": "Prone", "Ovr": "OVR", "Pot": "POT",
}

# Platoon splits of the current ratings: `<col>_L` / `<col>_R` (vs left / right -
# handed pitchers for a batter, batters for a pitcher) -> "CON vL" etc.
_SPLIT_SOURCES = {
    "contact_ovr": "Cntct", "gap_ovr": "Gap", "power_ovr": "Pow", "eye_ovr": "Eye",
    "avoid_k_ovr": "Ks", "stuff_ovr": "Stf", "movement_ovr": "Mov", "control_ovr": "Ctrl",
}
RATINGS_COLUMN_MAP.update(
    {
        f"{src}_{side[1]}": split_header(field, side)
        for field, src in _SPLIT_SOURCES.items()
        for side in SPLIT_SIDES
    }
)

# --- value maps for the columns that are codes rather than words --------------
HAND_NAMES = {"R": "Right", "L": "Left", "S": "Switch", "B": "Switch"}

# `Acc` -> the words `modifiers/scouting_accuracy_modifier.py` keys on.
SCT_ACC_NAMES = {
    "VH": "Very High", "H": "High", "A": "Average", "L": "Low", "VL": "Very Low",
}

# `GBType` / `FBType` integer code -> the pull-tendency words in
# `modifiers/batter_hit_profile_modifier.py` (comparisons only, so a wrong guess
# nudges a modifier rather than crashing). Pull vs Spray ordering unconfirmed.
GB_TENDENCY_NAMES = {"0": "Normal", "1": "Pull", "2": "Spray", "3": "Ex. Pull"}
FB_TENDENCY_NAMES = {"0": "Normal", "1": "Spray", "2": "Pull"}

# Individual-pitch columns (current + potential headers). The ratings CSV uses
# ``0`` for "doesn't throw this pitch"; OOTP exports leave it blank / "-". Left as
# ``0`` a phantom pitch slips into `GamePlayer.get_pitches()` and blows up the
# pitch-count modifier maps, so these are blanked when 0.
PITCH_COLUMNS = (
    "FB", "SI", "CT", "CB", "SL", "CH", "SP", "FO", "CC", "SC", "KN", "KC",
    "FBP", "SIP", "CTP", "CBP", "SLP", "CHP", "SPP", "FOP", "CCP", "SCP", "KNP", "KCP",
)

# integer level code -> level name, from StatsPlus's documented `Level` table
# (wiki.statsplus.net/web-tools/statsplus-api, "Reference tables"):
#   1 ml · 2 aaa · 3 aa · 4 a · 5 short a · 6 rookie · 7 indy · 8 international
#   10 college · 11 high school
# OOTP has only one full-season "A" level (code 4 covers every A-ball league), so
# there is no "A+". Code 0 is "no team" - a released pro shows here as a free
# agent; the amateur pools are filtered out upstream (`_is_amateur`).
LEVEL_NAMES = {
    "0": "FA", "1": "MLB", "2": "AAA", "3": "AA", "4": "A", "5": "A-",
    "6": "R", "7": "Indy", "8": "INT", "10": "NCAA", "11": "HS",
}

# Level shown for a player StatsPlus flags as international-complex (negative
# league id) - they carry their parent MLB club's id at level 1, so their raw
# `Level` code would otherwise read "MLB".
INTL_COMPLEX_LEVEL = "INT"

# Display order for the `Lev` column, best (highest) level first. Values not
# listed sort last, alphabetically. Shared by the web layer for the by-org team
# picker and the level filter.
LEVEL_ORDER = ["MLB", "AAA", "AA", "A", "A-", "R", "Indy", "INT", "NCAA", "HS", "FA"]

# `G/F` bucketed from the numeric `GB` column: (exclusive-upper-bound, label),
# then `GF_DEFAULT` above the last bound. Must resolve to one of the keys in
# `pitcher_scorer.rp_groundball_type_modifier_map` for every player.
GF_BUCKETS = ((40, "EX FB"), (47, "FB"), (53, "NEU"), (60, "GB"))
GF_DEFAULT = "EX GB"
# The five labels a valid `G/F` cell holds - `pitcher_scorer` keys its modifier
# maps on exactly these.
GF_LABELS = frozenset(label for _, label in GF_BUCKETS) | {GF_DEFAULT}


def _int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _is_amateur(ply: dict, level_code: str) -> bool:
    """Whether a player is in an amateur pool - the upcoming Rule 4 draft class or
    the international / undrafted amateur FA pool - rather than a real free agent.

    Both amateur pools sit at level 0 with no team, no org, and no history of
    affiliated ball; a genuine free agent (a released pro) carries pro service
    time or a `last_team_id`. `draft_eligible == 1` is the draft class exactly and
    is a strict subset of this; the rest are the international / undrafted pool.
    """
    if not ply or (level_code or "").strip() not in ("", "0"):
        return False
    if (ply.get("draft_eligible") or "").strip() == "1":
        return True
    never_pro = (
        _int(ply.get("pro_service_years"), 0) == 0
        and _int(ply.get("pro_service_days"), 0) == 0
    )
    no_last_team = (ply.get("last_team_id") or "").strip() in ("", "0")
    return never_pro and no_last_team


def _is_rule5_eligible(ply: dict, org_id: str) -> bool:
    """Whether an org's player is exposed in the upcoming Rule 5 draft. StatsPlus
    has no eligibility flag, so derive it from `/api/players/`:

    - `is_on_secondary` - on the 40-man roster, i.e. protected
    - `years_protected_from_rule_5` - OOTP's protection window, fixed at signing
      (5 if signed at 18 or younger, 4 if 19+; 0 for a few veterans). It does
      NOT count down.
    - `pro_service_years` - pro seasons served, counting the signing year but
      not the current season until the new-season rollover (a 2039 draftee
      shows 3 in Nov 2042). Hence the `+ 1` for the season in progress, which
      holds year-round: verified against `yfmlb` in Nov 2042, where a 2039
      college draftee (window 4, 3 years) is eligible and a 2039 HS draftee
      (window 5, 3 years) becomes eligible the following year.
    """
    if not ply or not org_id:
        return False
    if (ply.get("is_on_secondary") or "").strip() == "1":
        return False
    protected = _int(ply.get("years_protected_from_rule_5"))
    served = _int(ply.get("pro_service_years"))
    if protected is None or served is None:
        return False
    return served + 1 >= protected


def _is_intl_complex(rat: dict, ply: dict) -> bool:
    """StatsPlus flags an international-complex player with a NEGATIVE league id -
    `League` in the ratings CSV, `League ID` in the players CSV (documented at
    wiki.statsplus.net/web-tools/statsplus-api). These teenagers are carried on
    the parent MLB club's id at level 1, so without this check they'd be scored
    and grouped as big leaguers."""
    for value in ((rat or {}).get("League"), (ply or {}).get("League ID")):
        n = _int(value)
        if n is not None and n < 0:
            return True
    return False


def gf_from_gb(gb) -> str:
    """Bucket the numeric ratings `GB` column into a pitcher GB/FB profile."""
    n = _int(gb)
    if n is None:
        return "NEU"
    for upper, label in GF_BUCKETS:
        if n < upper:
            return label
    return GF_DEFAULT


def coerce_gf(value) -> str:
    """Return a valid `G/F` label. A snapshot written by an older build (before
    the numeric `GB` column was bucketed here) stored the raw rating in `G/F`;
    re-bucket anything that isn't already one of `GF_LABELS` so a stale data file
    doesn't `KeyError` the pitcher scorer."""
    text = (str(value).strip() if value is not None else "")
    if text in GF_LABELS:
        return text
    return gf_from_gb(text)


# ------------------------------------------------------------------- the context
# `league_snapshots` columns surfaced by `load_meta` (the old meta.json keys)
_META_COLUMNS = (
    "league_id", "version", "fetched_at", "last_checked_at", "player_count",
    "total_row_count", "league_date",
)


@dataclass
class LeagueSnapshotContext:
    """One league's stored snapshot: its `league_snapshots` row plus the files
    under ``$DATA_DIR/league_snapshots/<league_id>/``. Deliberately has none of
    the draft-class-only concepts (custom order, drafted players, upload file)."""

    league_id: str

    @property
    def base_dir(self) -> Path:
        return default_base_dir()

    @property
    def snapshot_dir(self) -> Path:
        return self.base_dir / "league_snapshots" / self.league_id

    @property
    def data_file(self) -> Path:
        return self.snapshot_dir / "players.csv"

    @property
    def teams_file(self) -> Path:
        return self.snapshot_dir / "teams.csv"

    def ensure_dirs(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.data_file.exists()

    def load_meta(self) -> dict:
        row = db.query_one(
            f"SELECT {', '.join(_META_COLUMNS)} FROM league_snapshots WHERE league_id = ?",
            (self.league_id,),
        )
        return dict(row) if row else {}


# --------------------------------------------------------------- join + rename
def _rows(csv_text: str):
    return csv.DictReader(io.StringIO(csv_text))


def _map_row(rat: dict, ply: dict, teams: dict) -> dict:
    row = {name: "" for name in SNAPSHOT_FIELDNAMES}

    for src, dst in RATINGS_COLUMN_MAP.items():
        value = rat.get(src)
        if value is not None:
            row[dst] = value

    row["B"] = HAND_NAMES.get((rat.get("Bats") or "").strip(), rat.get("Bats") or "")
    row["T"] = HAND_NAMES.get((rat.get("Throws") or "").strip(), rat.get("Throws") or "")
    row["SctAcc"] = SCT_ACC_NAMES.get(
        (rat.get("Acc") or "").strip(), rat.get("Acc") or ""
    )

    row["GBT"] = GB_TENDENCY_NAMES.get((rat.get("GBType") or "").strip(), "Normal")
    row["FBT"] = FB_TENDENCY_NAMES.get((rat.get("FBType") or "").strip(), "Normal")
    row["BBT"] = "Normal"  # no API source; model default
    row["G/F"] = gf_from_gb(rat.get("GB"))

    intl_complex = _is_intl_complex(rat, ply)
    level_code = ((ply.get("Level") if ply else "") or rat.get("LgLvl") or "").strip()
    row["Lev"] = (
        INTL_COMPLEX_LEVEL if intl_complex else LEVEL_NAMES.get(level_code, "")
    )

    # In-game league id of the player's team. StatsPlus negates it for the
    # international complex (see `_is_intl_complex`); store the magnitude so those
    # teenagers count toward their parent club's real league. Blank for a free
    # agent / unaffiliated player.
    league_code = _int(
        (rat.get("League") or (ply.get("League ID") if ply else "") or "").strip()
    )
    row["snap_league_id"] = str(abs(league_code)) if league_code else ""

    org_id = (
        (rat.get("Org") or "").strip()
        or (ply.get("Organization ID") if ply else "")
        or (ply.get("Parent Team ID") if ply else "")
        or (ply.get("Team ID") if ply else "")
    ).strip()
    # OOTP lists the 16 international sides (Japan, Cuba, China, ...) as top-level
    # "teams". A player whose org is one of those is in the international pool, not
    # a member of that club - treat them as unaffiliated so they don't show up as
    # a bogus org in the by-org view.
    if _is_national_team(org_id, teams):
        org_id = ""
    row["ORG"] = _resolve_org_name(org_id, teams)

    for col in PITCH_COLUMNS:
        if _int(row.get(col), 0) == 0:
            row[col] = ""

    row["ID"] = (rat.get("ID") or "").strip()
    row["Name"] = rat.get("Name") or ""

    team_id = (
        (rat.get("Team") or "").strip() or (ply.get("Team ID") if ply else "") or ""
    ).strip()
    # Keep the org but drop the roster team for a player who isn't actually on a
    # real affiliate: either StatsPlus flags him as international-complex (carried
    # on the parent MLB id at level 1), or his "team" is a top-level club (an MLB
    # parent, an independent league, a national team) while he plays below the
    # majors - the org-pool / complex slot. Otherwise he'd show up on the
    # big-league club in the by-team view.
    if team_id and (
        intl_complex
        or (level_code != "1" and _is_top_level_team(team_id, teams))
    ):
        team_id = ""
    row["snap_team_id"] = team_id
    row["snap_org_id"] = org_id
    # `/api/players/` reports MLB service as a floored whole-year count plus
    # leftover days; the potential ranking only wants players under a year, i.e.
    # `mlb_service_years == 0`. Missing players row (unjoined id) -> treat as 0.
    row["mlb_service_years"] = (
        (ply.get("mlb_service_years") if ply else "") or ""
    ).strip()
    row["is_amateur"] = "1" if _is_amateur(ply, level_code) else ""
    row["rule_5_eligible"] = (
        "1" if not row["is_amateur"] and _is_rule5_eligible(ply, org_id) else ""
    )
    return row


def _is_top_level_team(team_id: str, teams: dict) -> bool:
    team = teams.get((team_id or "").strip())
    return bool(team) and (team.get("Parent Team ID") or "").strip() in ("", "0")


def _is_national_team(team_id: str, teams: dict) -> bool:
    """The international sides (Japan, Cuba, ...) are the top-level teams with no
    nickname - real clubs (incl. the indy-league ones) always carry a nickname."""
    team = teams.get((team_id or "").strip())
    return (
        _is_top_level_team(team_id, teams)
        and bool(team)
        and not (team.get("Nickname") or "").strip()
    )


def _resolve_org_name(team_id: str, teams: dict) -> str:
    """Walk `Parent Team ID` up to the top-level (MLB / independent) club and
    return its name. StatsPlus's ratings `Org` is already the parent, but the
    `players` fallbacks (`Team ID`) can point at an affiliate."""
    seen = set()
    tid = (team_id or "").strip()
    while tid and tid != "0" and tid in teams and tid not in seen:
        seen.add(tid)
        team = teams[tid]
        parent = (team.get("Parent Team ID") or "").strip()
        if not parent or parent == "0":
            return team.get("Name") or ""
        tid = parent
    return teams.get(tid, {}).get("Name", "") if tid in teams else ""


def join_rows(ratings_csv: str, players_csv: str, teams_csv: str) -> list[dict]:
    """Left-join the ratings rows (the base population) onto players + teams and
    rename every column to its OOTP scouting-export header."""
    teams = {r["ID"]: r for r in _rows(teams_csv) if r.get("ID")}
    players = {r["ID"]: r for r in _rows(players_csv) if r.get("ID")}
    out = []
    for rat in _rows(ratings_csv):
        pid = (rat.get("ID") or "").strip()
        if not pid:
            continue
        out.append(_map_row(rat, players.get(pid, {}), teams))
    return out


# A stored snapshot older than this has its freshness re-checked against the
# league's in-game date (GET /api/date/) the next time the league page loads.
STALE_AFTER = timedelta(days=1)


def build_snapshot(
    ctx: LeagueSnapshotContext,
    ratings_csv: str,
    players_csv: str,
    teams_csv: str,
    *,
    league_date: str = None,
) -> LeagueSnapshotContext:
    """Pure transform + write: join the three CSV blobs, write `ctx.data_file`,
    stash the teams CSV, and record the snapshot row (bumping its `version`).
    `league_date` is the in-game date the data was pulled at, kept so a later
    load can tell the sim has advanced."""
    rows = join_rows(ratings_csv, players_csv, teams_csv)
    ctx.ensure_dirs()
    with open(ctx.data_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    ctx.teams_file.write_text(teams_csv)
    now = datetime.now(timezone.utc).isoformat()
    # `player_count` is the number the league page shows and is the count the
    # rankings actually work from: the amateur pools (draft class + international
    # / undrafted amateur FAs) are excluded from every ranking, so they don't
    # count as players here either. `total_row_count` keeps the raw snapshot size.
    ranked_pool = sum(1 for r in rows if r.get("is_amateur") != "1")
    db.execute(
        "INSERT INTO league_snapshots (league_id, fetched_at, last_checked_at, "
        "player_count, total_row_count, league_date) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(league_id) DO UPDATE SET version = version + 1, "
        "fetched_at = excluded.fetched_at, last_checked_at = excluded.last_checked_at, "
        "player_count = excluded.player_count, total_row_count = excluded.total_row_count, "
        "league_date = excluded.league_date",
        (ctx.league_id, now, now, ranked_pool, len(rows), league_date),
    )
    return ctx


def touch_checked(ctx: LeagueSnapshotContext, league_date: str = None) -> None:
    """Record that the snapshot was verified current (its `league_date` still
    matches the sim) so the freshness check stays quiet for another day."""
    db.execute(
        "UPDATE league_snapshots SET last_checked_at = ?, "
        "league_date = COALESCE(?, league_date) WHERE league_id = ?",
        (datetime.now(timezone.utc).isoformat(), league_date or None, ctx.league_id),
    )


def snapshot_age(ctx: LeagueSnapshotContext):
    """`timedelta` since the snapshot was last fetched or checked, or None if
    there is no snapshot / no usable timestamp."""
    meta = ctx.load_meta()
    stamp = meta.get("last_checked_at") or meta.get("fetched_at")
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when


def fetch_and_build(
    league: dict, *, cookie: str = None, on_phase=None
) -> LeagueSnapshotContext:
    """Fetch the four endpoints for `league` (a `web/leagues.py` dict) and build
    the stored snapshot. `cookie` defaults to the league's own StatsPlus cookie.

    `on_phase`, if given, is called with a short status string as each endpoint
    is pulled - the league refresh streams these to the page."""
    if not league or not league.get("league_url"):
        raise ValueError("League has no StatsPlus URL configured.")
    if cookie is None:
        from web.settings import cookie_header

        cookie = cookie_header(league)

    def _phase(msg):
        if on_phase:
            on_phase(msg)

    league_url = league["league_url"]
    league_date = None
    try:
        league_date = fetch_league_date(league_url, cookie)
    except StatsPlusError:
        pass  # non-fatal: the snapshot is still valid, just can't stamp the date
    _phase("Reading ratings from StatsPlus…")
    ratings_csv = fetch_ratings(league_url, cookie)
    _phase("Reading players from StatsPlus…")
    players_csv = fetch_players(league_url, cookie)
    _phase("Reading team rosters from StatsPlus…")
    teams_csv = fetch_teams(league_url, cookie)
    _phase("Building the snapshot…")

    ctx = LeagueSnapshotContext(league["id"])
    return build_snapshot(ctx, ratings_csv, players_csv, teams_csv, league_date=league_date)


# ------------------------------------------------------------------- ranking
#
# `ranked_rows(ctx, method)` scores the stored snapshot with one of the two
# league-view rankers and returns result rows (see `results_store`), so
# `web/service._player_payload` consumes a snapshot row exactly like a
# draft-class row (the `drafted*` / custom-order bits just come back empty).
#
# A full-league export is ~15k players and scoring it takes tens of seconds, so
# the run is stored (`results_store`, scope "league") and reused for as long as
# it was scored from the current snapshot `version`. The league refresh scores
# both methods up front; a request only ever re-scores if that failed.


def snapshot_version(ctx: LeagueSnapshotContext) -> int:
    return ctx.load_meta().get("version") or 0


def ranked_method_is_fresh(ctx: LeagueSnapshotContext, method: str) -> bool:
    """Whether the stored `method` ranking was scored from the current snapshot -
    i.e. it is ready to serve without a re-score. Drives the "model hasn't run
    yet" hint on the league page."""
    info = results_store.run_info(results_store.LEAGUE, ctx.league_id, method)
    return (
        info is not None
        and ctx.data_file.exists()
        and info["source_version"] == snapshot_version(ctx)
    )


def _score(ctx: LeagueSnapshotContext, method: str, progress=None) -> list[dict]:
    ranker = get_ranker_for_method(method)

    # The potential ranking is about players who haven't established themselves in
    # the majors yet, so it only scores players with under a year of MLB service
    # time (an OOTP service year is 172 days; `mlb_service_years` is already the
    # floored whole-year count, so "< 1 year" is exactly 0 / blank). The `overall`
    # ranking - and the draft-class pipeline, which carries no service-time
    # column - are unaffected.
    rookies_only = method == "potential"

    def _players():
        # Stream GamePlayers straight off disk so the batched ranker never holds
        # the whole ~15k-player pool in memory at once.
        with open(ctx.data_file, newline="") as f:
            for row in csv.DictReader(f):
                # Amateur pools (draft class + international / undrafted amateur
                # FAs) are not real rostered players - drop them from every
                # ranking, not just the potential one.
                if row.get("is_amateur") == "1":
                    continue
                if rookies_only and _int(row.get("mlb_service_years"), 0) >= 1:
                    continue
                # Heal a legacy data file that stored the raw `GB` rating here.
                row["G/F"] = coerce_gf(row.get("G/F"))
                yield GamePlayer(row)

    scored = ranker.rank(_players(), batch_size=DEFAULT_BATCH_SIZE, progress=progress)
    return [results_store.result_from_scored(s) for s in scored]


def ranked_rows(
    ctx: LeagueSnapshotContext, ranking_method: str, progress=None
) -> list[dict]:
    """Snapshot rows scored + ordered by `ranking_method` ("overall" or
    "potential"), best-first - the stored run when it is current, otherwise a
    fresh score that replaces it.

    `progress`, if given, is forwarded to the ranker and called with the running
    count of players scored - but only when it actually re-scores."""
    from scoring.model_cache import HEAVY_SCORING_LOCK

    if ranking_method not in LEAGUE_RANKING_METHODS:
        raise ValueError(
            f"League view supports {LEAGUE_RANKING_METHODS}, not {ranking_method!r}."
        )
    if not ctx.data_file.exists():
        raise FileNotFoundError(
            f"No league snapshot for {ctx.league_id!r}; refresh it first."
        )
    if not ranked_method_is_fresh(ctx, ranking_method):
        with HEAVY_SCORING_LOCK:
            # re-check: a concurrent caller may have scored it while we waited
            if not ranked_method_is_fresh(ctx, ranking_method):
                version = snapshot_version(ctx)
                results_store.save_run(
                    results_store.LEAGUE, ctx.league_id, ranking_method, version,
                    _score(ctx, ranking_method, progress),
                )
    return results_store.load_results(results_store.LEAGUE, ctx.league_id, ranking_method)
