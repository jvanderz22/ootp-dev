"""Which players in a class have already been drafted - the `drafted_picks` table.

Picks normally come from the StatsPlus draft API, keyed by the OOTP player id
(`save_picks`). The old scrape scripts only know a "POS First Last" `Selection`
string per pick; `resolve_selection_rows` matches those to ids by name +
position against the class dataset before they are saved.
"""
import db
from draft_class_files import _ctx
from get_game_players import get_game_players


def get_drafted_player_ids(ctx=None):
    return set(get_drafted_players_info(ctx).keys())


def get_drafted_players_info(ctx=None):
    rows = db.query(
        "SELECT player_id, name, team, round, round_pick, overall_pick "
        "FROM drafted_picks WHERE class_name = ?",
        (_ctx(ctx).name,),
    )
    return {
        r["player_id"]: {
            "name": r["name"],
            "team": r["team"],
            "round": r["round"],
            "round_selection": r["round_pick"],
            "overall_selection": r["overall_pick"],
        }
        for r in rows
    }


def save_drafted_info(ctx, info) -> None:
    """Replace the class's drafted picks with `info` ({player_id: {name, team,
    round, round_selection, overall_selection}})."""
    ctx = _ctx(ctx)
    with db.transaction() as conn:
        conn.execute("DELETE FROM drafted_picks WHERE class_name = ?", (ctx.name,))
        conn.executemany(
            "INSERT INTO drafted_picks (class_name, player_id, name, team, round, "
            "round_pick, overall_pick) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (ctx.name, pid, d.get("name", ""), d.get("team", ""), d.get("round", ""),
                 d.get("round_selection", ""), d.get("overall_selection", ""))
                for pid, d in info.items()
            ],
        )
        conn.execute(
            "UPDATE draft_classes SET revision = revision + 1 WHERE name = ?", (ctx.name,)
        )


def save_picks(ctx, picks) -> None:
    """Store StatsPlus `DraftPick`s; a repeated id keeps its last pick."""
    info = {}
    for pick in picks:
        pid = (pick.id or "").strip()
        if pid:
            info[pid] = {
                "name": (pick.name or "").strip(),
                "team": (pick.team or "").strip(),
                "round": (pick.round or "").strip(),
                "round_selection": (pick.pick or "").strip(),
                "overall_selection": (pick.overall or "").strip(),
            }
    save_drafted_info(ctx, info)


def _players_by_name(ctx):
    players_by_name = {}
    for player in get_game_players(ctx).game_players:
        name = player.name.lower()
        position = player.position.lower()
        if position in ("sp", "rp", "cl"):
            position = "p"
        players_by_name.setdefault(name, {})[position] = player
    return players_by_name


def resolve_selection_rows(ctx, rows):
    """{player_id: info} for scrape-format rows (`Round`, `Pick`, `Overall`,
    `Team`, `Selection` = "POS First Last"), matched by name + position."""
    players_by_name = _players_by_name(ctx)
    drafted = {}
    for drafted_player in rows:
        selection = (drafted_player.get("Selection") or "").split(" ")
        player_name_arr = selection[1:]
        if len(player_name_arr) < 1:
            continue
        if len(player_name_arr[-1]) == 1:
            player_name_arr = player_name_arr[:-1]
        player_name = " ".join(player_name_arr).lower()
        player_position = selection[0].lower()

        player = players_by_name.get(player_name, {}).get(player_position)
        if player is None:
            candidates = players_by_name.get(player_name)
            if candidates:
                player = next(iter(candidates.values()))
        if player is not None:
            drafted[player.id] = {
                "name": player_name,
                "team": drafted_player.get("Team", ""),
                "round": drafted_player.get("Round", ""),
                "round_selection": drafted_player.get("Pick", ""),
                "overall_selection": drafted_player.get("Overall", ""),
            }
    return drafted
