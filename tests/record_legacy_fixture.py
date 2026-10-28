"""One-off: record tests/fixtures/legacy_data_dir.tar.gz with the pre-SQLite app.

The tarball is a $DATA_DIR exactly as the file-based app (commit b6179fa) wrote
it, so `test_legacy_data_dir` can prove the SQLite importer reads a production
volume correctly. It only makes sense against that old code - once the app
stores data in SQLite this script would no longer produce the legacy layout, so
it refuses to run.

    python3 -m tests.record_legacy_fixture
"""
import csv
import io
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    if (REPO / "db.py").exists():
        sys.exit("db.py exists - this only records the legacy (pre-SQLite) layout.")

    data_dir = Path(tempfile.mkdtemp(prefix="legacy-data-"))
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["APP_PASSWORD"] = ""

    import league_snapshot
    from starlette.testclient import TestClient
    from tests import e2e_fixtures
    from tests import test_e2e_golden as t
    from web import service
    from web.app import app

    ratings, players, teams = e2e_fixtures.make_statsplus_csvs()
    league_snapshot.fetch_ratings = lambda *a, **k: ratings
    league_snapshot.fetch_players = lambda *a, **k: players
    league_snapshot.fetch_teams = lambda *a, **k: teams
    league_snapshot.fetch_league_date = lambda *a, **k: t.LEAGUE_DATE
    draft_csv = e2e_fixtures.make_draft_class_csv()
    service.fetch_draft_picks = lambda *a, **k: e2e_fixtures.draft_picks(draft_csv)

    client = TestClient(app)
    scratch = Path(tempfile.mkdtemp(prefix="legacy-uploads-"))
    lid = t.create_league(client)["id"]
    assert lid == t.LEGACY_LEAGUE

    # class 1: draft_class model, pinned to the league, API drafted picks, custom order
    t.upload_class(client, scratch, name="fx-draft")
    t.gql(client, f'mutation {{ setClassLeague(name: "fx-draft", leagueId: "{lid}") {{ name }} }}')
    t.gql(client, 'mutation { refreshDraftedFromStatsPlus(name: "fx-draft") { draftedCount } }')
    ids = [r["id"] for r in t.ranked(client, "id", name="fx-draft", all=True)["rows"]]
    order = list(reversed(ids[:6])) + ids[6:]
    t.gql(client, 'mutation($o: [ID!]!) { saveCustomOrder(name: "fx-draft", order: $o) { name } }', o=order)

    # class 2: overall model, no league, legacy name-scrape drafted file
    second = e2e_fixtures.make_draft_class_csv(n=60, seed=3)
    t.upload_class(client, scratch, name="fx-overall", method="overall", csv_text=second)
    rows = list(csv.DictReader(io.StringIO(second)))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["Round", "Pick", "Overall", "Team", "Selection"])
    writer.writeheader()
    for n, row in enumerate(rows[::9]):
        writer.writerow({"Round": "1", "Pick": str(n + 1), "Overall": str(n + 1),
                         "Team": "Pirates", "Selection": f"{row['POS']} {row['Name']}"})
    writer.writerow({"Round": "2", "Pick": "1", "Overall": "9", "Team": "Bison",
                     "Selection": "SS Nobody Known"})
    (data_dir / "processed_classes" / "fx-overall" / "drafted_players.csv").write_text(buf.getvalue())

    # league snapshot, both methods scored to disk by the background refresh
    t.gql(client, f'mutation {{ refreshLeagueSnapshot(leagueId: "{lid}") {{ state }} }}')
    while t.gql(client, f'{{ leagueRefreshStatus(leagueId: "{lid}") {{ state }} }}')[
        "leagueRefreshStatus"]["state"] == "running":
        time.sleep(0.2)

    out = REPO / "tests" / "fixtures" / "legacy_data_dir.tar.gz"
    out.parent.mkdir(exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        for path in sorted(data_dir.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(data_dir)))
    print(f"wrote {out} ({out.stat().st_size:,} bytes) from {data_dir}")


if __name__ == "__main__":
    main()
