"""Season stats pulled from StatsPlus and kept per league: the outcomes the
ranking redesign is fit against (see plans/ranking-architecture-plan.md).

    $DATA_DIR/league_stats/<league_id>/<kind>/<year>.csv     kind = bat | pitch | field

Each file holds one season at every level - fetched one `/api/lgdata/` league
at a time, MLB down to rookie ball - and every split (`split_id` 1 overall,
2 vs L, 3 vs R). Rows keep StatsPlus's columns, including `league_id` /
`level_id`. Past seasons don't change, so one already on disk is skipped unless
`refetch`; the season in progress is always refetched. A season StatsPlus has
no rows for (e.g. the upcoming one in the preseason) isn't written.

    python league_stats.py <league_id> <first_year>[-<last_year>] [--refetch]
"""
import argparse
import csv
import io
import sys
import time
from pathlib import Path

import statsplus_api
from context import default_base_dir

KINDS = ("bat", "pitch", "field")
# A full backfill is a few hundred requests; don't fire them back to back.
REQUEST_PAUSE = 0.2


def stats_dir(league_id: str) -> Path:
    return default_base_dir() / "league_stats" / league_id


def stats_file(league_id: str, kind: str, year: int) -> Path:
    return stats_dir(league_id) / kind / f"{year}.csv"


def league_ids(league_url: str, cookie: str) -> list:
    """Every in-game league id, majors first."""
    leagues = statsplus_api.fetch_league_data(league_url, cookie)["leagues"]
    return [
        lg["league_id"]
        for lg in sorted(leagues, key=lambda lg: (lg.get("level") or 0, lg["league_id"]))
    ]


def pull_season(league_url: str, cookie: str, kind: str, year: int, lids) -> tuple:
    """One season of `kind` across `lids`, as (header, rows)."""
    header, rows = [], []
    for lid in lids:
        text = statsplus_api.fetch_player_stats(league_url, cookie, kind, year, lid=lid)
        reader = csv.DictReader(io.StringIO(text))
        for col in reader.fieldnames or []:
            if col not in header:
                header.append(col)
        rows.extend(reader)
        time.sleep(REQUEST_PAUSE)
    return header, rows


def _write(path: Path, header: list, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def pull(league: dict, years, *, refetch=False, kinds=KINDS, cookie=None, log=print) -> list:
    """Fetch and store `years` of stats for `league` (a `web/leagues.py`
    dict). Returns the files written."""
    if cookie is None:
        from web.settings import cookie_header

        cookie = cookie_header(league)
    url = league["league_url"]
    current = int(statsplus_api.fetch_league_date(url, cookie)[:4])
    lids = league_ids(url, cookie)
    written = []
    for year in years:
        for kind in kinds:
            path = stats_file(league["id"], kind, year)
            if path.exists() and year < current and not refetch:
                continue
            header, rows = pull_season(url, cookie, kind, year, lids)
            if not rows:
                log(f"{kind} {year}: no rows")
                continue
            _write(path, header, rows)
            written.append(path)
            log(f"{kind} {year}: {len(rows)} rows")
    return written


def _years(spec: str) -> range:
    first, _, last = spec.partition("-")
    return range(int(first), int(last or first) + 1)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("league_id")
    p.add_argument("years", help="a season or a range, e.g. 2042 or 2034-2042")
    p.add_argument("--refetch", action="store_true", help="refetch seasons already on disk")
    args = p.parse_args(argv)

    from web.leagues import get_league
    from web.settings import cookie_header

    league = get_league(args.league_id)
    if not league or not league.get("league_url") or not cookie_header(league):
        sys.exit(f"League {args.league_id!r} isn't set up with a StatsPlus URL and cookie.")
    pull(league, _years(args.years), refetch=args.refetch)


if __name__ == "__main__":
    main()
