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
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from context import default_base_dir
from io_utils import atomic_write_json
from models.game_players import PLAYER_FIELDS, GamePlayer
from ranking_csv import RANKED_PLAYER_FIELDNAMES
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

# Non-OOTP bookkeeping columns kept alongside the scouting grid so the web layer
# can group a snapshot by roster team / parent org. `GamePlayer` ignores columns
# it doesn't know, so these are invisible to the rankers.
SNAPSHOT_META_FIELDS = ["snap_team_id", "snap_org_id"]
SNAPSHOT_FIELDNAMES = OUTPUT_FIELDNAMES + SNAPSHOT_META_FIELDS


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

# integer level code -> level name. UNVERIFIED beyond "1 == MLB" and "0 ==
# unaffiliated" (those rows have Team / Org / League / Level all 0 - free agents
# and the amateur pool).
LEVEL_NAMES = {
    "0": "FA", "1": "MLB", "2": "AAA", "3": "AA", "4": "A+", "5": "A", "6": "A-",
}

# `G/F` bucketed from the numeric `GB` column: (exclusive-upper-bound, label),
# then `GF_DEFAULT` above the last bound. Must resolve to one of the keys in
# `pitcher_scorer.rp_groundball_type_modifier_map` for every player.
GF_BUCKETS = ((40, "EX FB"), (47, "FB"), (53, "NEU"), (60, "GB"))
GF_DEFAULT = "EX GB"


def _int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def gf_from_gb(gb) -> str:
    """Bucket the numeric ratings `GB` column into a pitcher GB/FB profile."""
    n = _int(gb)
    if n is None:
        return "NEU"
    for upper, label in GF_BUCKETS:
        if n < upper:
            return label
    return GF_DEFAULT


# ------------------------------------------------------------------- the context
@dataclass
class LeagueSnapshotContext:
    """Paths for one league's stored snapshot, rooted at
    ``<base>/league_snapshots/<league_id>/``. Deliberately has none of the
    draft-class-only concepts (custom order, drafted players, upload file)."""

    league_id: str
    base_dir: Path = field(default_factory=default_base_dir)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    @property
    def snapshot_dir(self) -> Path:
        return self.base_dir / "league_snapshots" / self.league_id

    @property
    def data_file(self) -> Path:
        return self.snapshot_dir / "players.csv"

    @property
    def meta_file(self) -> Path:
        return self.snapshot_dir / "meta.json"

    @property
    def teams_file(self) -> Path:
        return self.snapshot_dir / "teams.csv"

    def ranker_dir(self, ranker) -> Path:
        name = ranker if isinstance(ranker, str) else ranker.__class__.__name__
        folder = self.snapshot_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def ranked_players_file(self, ranker) -> Path:
        return self.ranker_dir(ranker) / "ranked_players.csv"

    def ensure_dirs(self) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.data_file.exists()

    def load_meta(self) -> dict:
        try:
            with open(self.meta_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


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

    level_code = ((ply.get("Level") if ply else "") or rat.get("LgLvl") or "").strip()
    row["Lev"] = LEVEL_NAMES.get(level_code, "")

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
    # A non-MLB player whose "team" is actually a top-level club (an MLB parent,
    # an independent league, a national team) isn't on a real affiliate roster -
    # that's the international-complex / org-pool slot. Keep the org, drop the
    # team so they don't show up on the big-league club in the by-team view.
    if team_id and level_code != "1" and _is_top_level_team(team_id, teams):
        team_id = ""
    row["snap_team_id"] = team_id
    row["snap_org_id"] = org_id
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
    stash the teams CSV, and write `meta.json`. `league_date` is the in-game date
    the data was pulled at, kept so a later load can tell the sim has advanced."""
    rows = join_rows(ratings_csv, players_csv, teams_csv)
    ctx.ensure_dirs()
    with open(ctx.data_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    ctx.teams_file.write_text(teams_csv)
    now = datetime.now(timezone.utc).isoformat()
    atomic_write_json(
        ctx.meta_file,
        {
            "league_id": ctx.league_id,
            "fetched_at": now,
            "last_checked_at": now,
            "player_count": len(rows),
            "league_date": league_date,
        },
    )
    return ctx


def touch_checked(ctx: LeagueSnapshotContext, league_date: str = None) -> None:
    """Record that the snapshot was verified current (its `league_date` still
    matches the sim) so the freshness check stays quiet for another day."""
    meta = ctx.load_meta()
    if not meta:
        return
    meta["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    if league_date:
        meta["league_date"] = league_date
    atomic_write_json(ctx.meta_file, meta)


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


def fetch_and_build(league: dict, *, base_dir=None, cookie: str = None) -> LeagueSnapshotContext:
    """Fetch the four endpoints for `league` (a `web/leagues.py` dict) and build
    the stored snapshot. `cookie` defaults to the app-wide StatsPlus cookie."""
    if not league or not league.get("league_url"):
        raise ValueError("League has no StatsPlus URL configured.")
    if cookie is None:
        from web.settings import cookie_header, load_settings

        cookie = cookie_header(load_settings())

    league_url = league["league_url"]
    league_date = None
    try:
        league_date = fetch_league_date(league_url, cookie)
    except StatsPlusError:
        pass  # non-fatal: the snapshot is still valid, just can't stamp the date
    ratings_csv = fetch_ratings(league_url, cookie)
    players_csv = fetch_players(league_url, cookie)
    teams_csv = fetch_teams(league_url, cookie)

    ctx = LeagueSnapshotContext(
        league["id"], base_dir=base_dir or default_base_dir()
    )
    return build_snapshot(ctx, ratings_csv, players_csv, teams_csv, league_date=league_date)


# ------------------------------------------------------------- ranking + cache
#
# `ranked_rows(ctx, method)` scores the stored snapshot with one of the two
# league-view rankers and returns rows in `ranking_csv.RANKED_PLAYER_FIELDNAMES`
# shape, so `web/service._player_payload` consumes a snapshot row exactly like a
# draft-class row (the `drafted*` / custom-order bits just come back empty).
#
# A full-league export is ~15k players and scoring it takes tens of seconds, so
# the result is cached two ways: on disk as `ctx.ranked_players_file(ranker)`
# (rebuilt when `players.csv` is newer) and in a small in-process LRU keyed on
# `(snapshot_dir, method)`. The in-memory entry lives until the snapshot file's
# mtime changes (a refresh) or it's evicted as least-recently-used - no TTL.

_MAX_CACHED_LEAGUES = 2
_MAX_RANKED_ENTRIES = _MAX_CACHED_LEAGUES * len(LEAGUE_RANKING_METHODS)
_ranked_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_ranked_cache_lock = threading.Lock()


def _ranked_row(index: int, s) -> dict:
    return {
        "overall_ranking": index,
        "model_ranking": index,
        "ranking_difference": 0,
        "id": s.id,
        "name": s.name,
        "position": s.position,
        "age": s.age,
        "model_score": round(s.overall_score, 2),
        "position_player_score": s.position_player_score,
        "fielding_score_component": s.fielding_score_component,
        "batting_score_component": s.batting_score_component,
        "pitcher_score": s.pitcher_score,
        "starter_component": s.starter_component,
        "reliever_component": s.reliever_component,
        "running_score_component": s.running_score_component,
        "in_game_overall": s.in_game_overall,
        "in_game_potential": s.in_game_potential,
        "demand": s.demand or "",
        "raw_overall_score": s.raw_overall_score,
        "components": s.components,
    }


def _score_and_write(ctx: LeagueSnapshotContext, method: str, out_file: Path) -> list[dict]:
    from scoring.model_cache import HEAVY_SCORING_LOCK

    with HEAVY_SCORING_LOCK:
        return _score_and_write_locked(ctx, method, out_file)


def _score_and_write_locked(
    ctx: LeagueSnapshotContext, method: str, out_file: Path
) -> list[dict]:
    ranker = get_ranker_for_method(method)

    def _players():
        # Stream GamePlayers straight off disk so the batched ranker never holds
        # the whole ~15k-player pool in memory at once.
        with open(ctx.data_file, newline="") as f:
            for row in csv.DictReader(f):
                yield GamePlayer(row)

    scored = ranker.rank(_players(), batch_size=DEFAULT_BATCH_SIZE)
    rows = [_ranked_row(i, s) for i, s in enumerate(scored)]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RANKED_PLAYER_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def _ranked_file_for(ctx: LeagueSnapshotContext, method: str) -> Path:
    return ctx.ranked_players_file(get_ranker_for_method(method).__class__.__name__)


def ranked_method_is_fresh(ctx: LeagueSnapshotContext, method: str) -> bool:
    """Whether `ranked_players.csv` for `method` exists and is at least as new as
    the snapshot data file - i.e. this ranking is ready to serve without a
    re-score. Drives the "model hasn't run yet" hint on the league page."""
    try:
        return (
            _ranked_file_for(ctx, method).stat().st_mtime
            >= ctx.data_file.stat().st_mtime
        )
    except (FileNotFoundError, ValueError):
        return False


def _disk_rows(ctx: LeagueSnapshotContext, method: str) -> list[dict]:
    """Read the cached `ranked_players.csv` if it is at least as new as the
    snapshot data file, otherwise re-score and rewrite it."""
    out_file = _ranked_file_for(ctx, method)
    if ranked_method_is_fresh(ctx, method):
        with open(out_file, newline="") as f:
            return list(csv.DictReader(f))
    return _score_and_write(ctx, method, out_file)


def ranked_rows(ctx: LeagueSnapshotContext, ranking_method: str) -> list[dict]:
    """Snapshot rows scored + ordered by `ranking_method` ("overall" or
    "potential"), best-first, served from the process cache when warm."""
    if ranking_method not in LEAGUE_RANKING_METHODS:
        raise ValueError(
            f"League view supports {LEAGUE_RANKING_METHODS}, not {ranking_method!r}."
        )
    if not ctx.data_file.exists():
        raise FileNotFoundError(
            f"No league snapshot for {ctx.league_id!r}; refresh it first."
        )

    src_mtime = ctx.data_file.stat().st_mtime
    key = (str(ctx.snapshot_dir), ranking_method)
    with _ranked_cache_lock:
        cached = _ranked_cache.get(key)
        if cached is not None and cached["src_mtime"] == src_mtime:
            _ranked_cache.move_to_end(key)  # mark most-recently-used
            return cached["rows"]

    rows = _disk_rows(ctx, ranking_method)

    with _ranked_cache_lock:
        _ranked_cache[key] = {"src_mtime": src_mtime, "rows": rows}
        _ranked_cache.move_to_end(key)
        while len(_ranked_cache) > _MAX_RANKED_ENTRIES:
            _ranked_cache.popitem(last=False)
    return rows


def evict_ranked_cache(league_id=None) -> None:
    """Drop cached ranked rows - all leagues, or one. Call after a refresh."""
    with _ranked_cache_lock:
        if league_id is None:
            _ranked_cache.clear()
            return
        marker = f"league_snapshots/{league_id}"
        for key in [k for k in _ranked_cache if marker in k[0]]:
            del _ranked_cache[key]
