#!/usr/bin/env bash
# Seed a scratch DATA_DIR, start the web app on it, drive it in headless
# Chrome, stop it. Run from the repo root:
#
#   .claude/skills/run-ootp-dev/smoke.sh OUT_DIR [DATASET_CSV]
#
# OUT_DIR gets data/ (the scratch DATA_DIR), server.log and the screenshots.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=$(mkdir -p "$1" && cd "$1" && pwd)
csv=${2:-}
port=${PORT:-8091}

[ -d "$here/node_modules/playwright-core" ] || npm install --prefix "$here" --silent
[ -f frontend/dist/draft-web/browser/index.html ] || { echo "build the frontend first: (cd frontend && npx ng build)"; exit 1; }

if [ -n "$csv" ]; then
  activate/bin/python "$here/seed.py" "$out/data" --csv "$csv"
  class=$(basename "$csv" .csv)
else
  activate/bin/python "$here/seed.py" "$out/data"
  class=smoke-class
fi

if lsof -ti:"$port" -sTCP:LISTEN >/dev/null; then echo "port $port is taken"; exit 1; fi
DATA_DIR="$out/data" APP_PASSWORD= activate/bin/uvicorn web.app:app --port "$port" > "$out/server.log" 2>&1 &
server=$!
trap 'kill $server 2>/dev/null; wait $server 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do curl -sf "localhost:$port/healthz" >/dev/null && break; sleep 1; done

node "$here/drive.mjs" "$class" "$out" "http://localhost:$port"
