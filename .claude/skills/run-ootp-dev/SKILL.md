---
name: run-ootp-dev
description: Run, start, drive or screenshot the OOTP draft web app (uvicorn web.app:app + the Angular SPA) against a scratch DATA_DIR; smoke-test the v2/legacy engine toggle, the Pre-dem columns and the player card's score ledger in headless Chrome; query the GraphQL API with curl.
---

# Run the OOTP draft web app

The app is a Starlette/Ariadne GraphQL server (`web/app.py`) that also serves
the built Angular SPA from `frontend/dist/`. Drive it with the scripts in this
directory: `seed.py` builds a scratch `DATA_DIR`, `drive.mjs` drives headless
Chrome through `playwright-core`, and `smoke.sh` chains seed → launch → drive →
stop. Paths below are relative to the repo root. Verified on macOS with system
Google Chrome.

## Prerequisites

- The Python 3.11 venv at `activate/` with `requirements.txt` installed.
- Node with `frontend/node_modules` installed (`cd frontend && npm ci`).
- Google Chrome at `/Applications/Google Chrome.app`. Point `CHROME=` at another binary to override it.

## Build

```bash
(cd frontend && npx ng build)
```

## Run (agent path)

```bash
.claude/skills/run-ootp-dev/smoke.sh "$SCRATCH/smoke"                                          # synthetic 80-player class
.claude/skills/run-ootp-dev/smoke.sh "$SCRATCH/smoke-real" fly_data/datasets/yfmlb-2042-draft.csv  # a real export
```

On the first run it installs `playwright-core` into this directory (gitignored).
Each run then:

- seeds `OUT/data` and scores the class under both engines;
- starts uvicorn on `:8091` (or `PORT`), logging to `OUT/server.log`;
- runs the checks, prints `ok`/`FAIL` lines and exits 1 on any failure;
- writes `1-table-v2.png`, `2-card-v2.png`, `3-table-legacy.png` and `4-card-legacy.png` (or `error.png`) to `OUT`;
- stops the server.

The whole run takes about 16 s. Look at the screenshots.

To poke a running server by hand:

```bash
activate/bin/python .claude/skills/run-ootp-dev/seed.py "$SCRATCH/data"
DATA_DIR="$SCRATCH/data" APP_PASSWORD= activate/bin/uvicorn web.app:app --port 8091 > "$SCRATCH/server.log" 2>&1 &
curl -s localhost:8091/graphql/ -H 'content-type: application/json' -H 'X-Ranking-Engine: legacy' \
  -d '{"query":"{ rankedPlayers(name: \"smoke-class\", pageSize: 2) { rows { name modelScore preDemandRank source { engine } } } }"}'
lsof -ti:8091 -sTCP:LISTEN | xargs kill
```

To drive a server that's already running, edit `drive.mjs` or run it directly:
`node .claude/skills/run-ootp-dev/drive.mjs CLASS OUT_DIR [BASE_URL]`.

## Test

```bash
activate/bin/python -m pytest -q
```

## Gotchas

- **The SPA always shows its login form until sessionStorage holds `ootp-draft-auth`,** even when `APP_PASSWORD` is empty and the server accepts anything. `drive.mjs` seeds a dummy Basic token with `addInitScript`.
- **The engine comes from the `X-Ranking-Engine` header** (or `?engine=` on downloads), not from a GraphQL argument. An unknown value silently falls back to v2. Switching engines in the UI reloads the page, so wait for navigation.
- **POST to `/graphql/` with the trailing slash.** `/graphql` answers 307.
- **The legacy card fills in after the breakdown query,** so the driver waits about 1.5 s before checking there's no ledger.
- **`seed.py` has to set `DATA_DIR` before importing `db`.** Run it from the repo root, so it can import `tests.e2e_fixtures`.
- **`fly_data/` is a local copy of production data and is gitignored.** On a clean checkout, use the synthetic class.
- **Background `&` jobs can't be stopped with `kill %1`** in the agent shell. Kill by port.

## Troubleshooting

- **`port 8091 is taken`:** a previous server is still up. Run `lsof -ti:8091 -sTCP:LISTEN | xargs kill`.
- **`build the frontend first`:** `frontend/dist` is missing. Run the Build step.
- **Prod shows `No module named 'ranking'`:** the Dockerfile copies packages one by one. A new package needs its own `COPY` line, and `tests/test_dockerfile.py` checks for it.
