"""Which players in the current class have already been drafted.

Two on-disk formats are supported for processed_classes/<class>/drafted_players.csv:

* API format (statsplus_api.write_drafted_players_file): has an ``id`` column -
  the OOTP player id, matched exactly against the dataset.
* Legacy scrape format: has a ``Selection`` column like "SS Bryce Rainer" that
  has to be matched by name + position.
"""
import csv
import os

from draft_class_files import get_draft_class_drafted_players_file
from get_game_players import get_game_players


def get_drafted_player_ids(ctx=None):
    return set(get_drafted_players_info(ctx).keys())


def get_drafted_players_info(ctx=None):
    path = get_draft_class_drafted_players_file(ctx)
    if not os.path.exists(path):
        return {}

    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
        rows = list(reader)

    if "id" in fieldnames:
        return _info_from_api_rows(rows)
    return _info_from_legacy_rows(ctx, rows)


def _info_from_api_rows(rows):
    drafted = {}
    for row in rows:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        pid = norm.get("id")
        if not pid:
            continue
        drafted[pid] = {
            "name": norm.get("name", ""),
            "team": norm.get("team", ""),
            "round": norm.get("round", ""),
            "round_selection": norm.get("pick", ""),
            "overall_selection": norm.get("overall", ""),
        }
    return drafted


def _players_by_name(ctx):
    players_by_name = {}
    for player in get_game_players(ctx).game_players:
        name = player.name.lower()
        position = player.position.lower()
        if position in ("sp", "rp", "cl"):
            position = "p"
        players_by_name.setdefault(name, {})[position] = player
    return players_by_name


def _info_from_legacy_rows(ctx, rows):
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
