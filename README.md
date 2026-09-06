# OOTP draft ranking

Scores and ranks OOTP draft classes with an XGBoost-based model, and produces a
StatsPlus / C+ preference-list CSV. Usable two ways:

- **Web app** (`web/` + `frontend/`) — upload a class, view the ranked table,
  switch classes, hand-reorder the ranking, download the C+ CSV, pull drafted
  players from the StatsPlus API.
- **CLI** (original scripts) — still works, driven by `constants.py`.

## Web app

### Architecture

```
Angular 22 SPA  --POST /graphql/-->  Ariadne GraphQL (Python, ASGI)  -->  ranking pipeline
                                     serves the built SPA + /download/<class>/upload.csv
```

- Data lives on the filesystem: `datasets/<class>.csv` + `processed_classes/<class>/…`
  under `$DATA_DIR` (defaults to the repo root; set to a volume in production).
- `leagues.json` under `$DATA_DIR` holds the leagues (name + StatsPlus URL +
  optional `lid` + that league's `sessionid` / `csrftoken`); each draft class is
  assigned to one (its `league_id` lives in the class's `config.json`). The
  cookie values live only on the (private) data volume and are never returned to
  the client — the API exposes only `hasSessionid` / `hasCsrftoken`.
- Whole app is behind HTTP Basic auth when `APP_PASSWORD` is set.

### StatsPlus configuration

"Refresh drafted" calls `<the class's league URL>/api/draftv2/` to pull the picks
made so far and mark those players drafted. StatsPlus has **no API key** — the
endpoint authenticates with your browser **session cookie**, and its login page is
behind a CAPTCHA, so the cookie has to be copied by hand. On the **Settings**
page: create one **League** per StatsPlus association (name + URL + optional
`lid`) and, in the same league form, paste that league's session cookie. Every
setting below is **per league**.

| Setting            | Notes                                                                                                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **League URL**     | Full URL (`https://statsplus.net/yfmlb/`, `https://atl-01.statsplus.net/wbf/`) or a bare slug (`yfmlb`) — both are normalised. Only `*.statsplus.net` hosts are accepted.            |
| **Session cookie** | `sessionid` + `csrftoken`, entered in the league form. A blank value on edit keeps what's stored.                                                                                  |
| **`lid`**          | Optional, only for associations that run multiple drafts.                                                                                                                          |

On upgrade, an existing app-wide `STATSPLUS_LEAGUE_URL` / `web_config.json`
`league_url` is folded into one league automatically, and any app-wide
`sessionid` / `csrftoken` (from `web_config.json` or the `STATSPLUS_SESSIONID`
/ `STATSPLUS_CSRFTOKEN` / `STATSPLUS_COOKIE` env vars) is seeded onto every
existing league that doesn't have its own — once.

To get the cookie: log into that league at statsplus.net in a browser →
DevTools → Application → Cookies → the StatsPlus host → copy the `sessionid` and
`csrftoken` values → paste them into the league form. It expires after a while;
when "Refresh drafted" reports an auth error, re-paste a fresh one. Everything
else in the app works without it — it's only needed to auto-populate the drafted
list.

### Run locally

Backend (port 8000):

```bash
source activate/bin/activate
DEV=1 DATA_DIR=./ uvicorn web.app:app --reload --port 8000
```

Frontend dev server (port 4200, proxies `/graphql` + `/download` to :8000):

```bash
cd frontend
npm install
npm start          # http://localhost:4200
```

Or run the whole thing from one process (build the SPA first):

```bash
cd frontend && npm run build && cd ..
APP_PASSWORD=secret uvicorn web.app:app --port 8080     # http://localhost:8080
```

### Deploy (Fly.io, free tier)

```bash
fly launch --no-deploy            # creates the app from fly.toml
fly volumes create draft_data --size 1
fly secrets set APP_PASSWORD=... [STATSPLUS_COOKIE=...]   # leagues are added in-app
fly deploy
```

The image bundles `training_data/`; `datasets/` and `processed_classes/` live on
the `draft_data` volume so uploads survive redeploys. 512 MB RAM is enough for the
XGBoost/scikit-learn models (they train once at startup).

### GraphQL

Schema: `web/schema.graphql`. Key operations:

| Operation                                           | Purpose                                                   |
| --------------------------------------------------- | --------------------------------------------------------- |
| `draftClasses` / `rankedPlayers(name)`              | list classes / ranked players in resolved order           |
| `uploadDraftClass(name, rankingMethod, file)`       | upload an OOTP HTML export or converted CSV, then process |
| `setRankingMethod` / `reprocessDraftClass`          | re-run the pipeline                                       |
| `saveCustomOrder(name, order)` / `clearCustomOrder` | manual drag-and-drop ordering                             |
| `refreshDraftedFromStatsPlus(name)`                 | pull drafted picks from the class's league `…/api/draftv2/` |
| `leagues` / `createLeague` / `updateLeague` / `deleteLeague` / `setClassLeague` | manage leagues (incl. per-league URL + session cookie) + class assignment |

C+ CSV download is a plain route: `GET /download/<class>/upload.csv`.

### Tests

```bash
pytest            # 18 tests; the "slow" ones train the models (~1 min total)
```

## CLI (original workflow)

Activate the virtual env: `source activate/bin/activate`

```bash
# Import a class from an exported game file
python3 load_draft_class.py -c draft-class-name -f /path/to/file.html

# Set DRAFT_CLASS_NAME in constants.py, then run evals
python3 run.py                        # -> processed_classes/<class>/DraftClassRanker/ranked_players.csv
                                      #    + upload_ranked_players.csv

python3 print_evals.py                # top available players
python3 print_org_summaries.py        # org summaries
```

`ranking_method` (in `processed_classes/<class>/config.json`): `draft_class`,
`potential`, `overall`.

The Selenium-based `import_drafted_players.py` / `upload_drafted_players.py` are
superseded by the StatsPlus API path in the web app but still present.
