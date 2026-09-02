#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Deploy this project to Fly.io using the repo's configured Dockerfile and volume layout.

Usage:
  ./deploy_fly.sh --app-password "secret" [--league-url "https://..." --cookie "sessionid=...; csrftoken=..." ]

Environment variables also work:
  APP_PASSWORD=secret STATSPLUS_LEAGUE_URL=... STATSPLUS_COOKIE="..." ./deploy_fly.sh

Required:
  --app-password, APP_PASSWORD

Optional:
  --app-name       default: ootp-draft
  --region         default: iad
  --volume-name    default: draft_data
  --volume-size    default: 1
  --league-url     default: $STATSPLUS_LEAGUE_URL
  --cookie         default: $STATSPLUS_COOKIE
  --help

This script follows the deploy steps documented in the repo:
  1. fly launch --no-deploy
  2. fly volumes create draft_data --size 1
  3. fly secrets set APP_PASSWORD=... [STATSPLUS_*]
  4. fly scale count 1 --max-per-region 1   (budget guard: never run >1 machine)
  5. fly deploy

Budget note: this does NOT set the account spend limit. After the first deploy,
open Dashboard -> your org -> Billing -> Spend limits and set a hard monthly cap.
That is the only backstop that a bug or a traffic flood cannot run past.
EOF
}

# Auto-load repo-local secrets (.env is gitignored) so APP_PASSWORD / STATSPLUS_*
# don't have to be exported by hand. Command-line flags still override these.
if [[ -f "$(dirname "$0")/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$(dirname "$0")/.env"
  set +a
fi

APP_NAME="ootp-draft"
REGION="iad"
VOLUME_NAME="draft_data"
VOLUME_SIZE="1"
APP_PASSWORD="${APP_PASSWORD:-}"
STATSPLUS_LEAGUE_URL="${STATSPLUS_LEAGUE_URL:-}"
STATSPLUS_COOKIE="${STATSPLUS_COOKIE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-name)
      APP_NAME="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --volume-name)
      VOLUME_NAME="$2"
      shift 2
      ;;
    --volume-size)
      VOLUME_SIZE="$2"
      shift 2
      ;;
    --app-password)
      APP_PASSWORD="$2"
      shift 2
      ;;
    --league-url)
      STATSPLUS_LEAGUE_URL="$2"
      shift 2
      ;;
    --cookie)
      STATSPLUS_COOKIE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$APP_PASSWORD" ]]; then
  echo "APP_PASSWORD is required. Pass --app-password or set APP_PASSWORD in the environment." >&2
  exit 1
fi

if ! command -v fly >/dev/null 2>&1 && ! command -v flyctl >/dev/null 2>&1; then
  echo "Fly CLI is not installed or not on PATH." >&2
  echo "Install it first: https://fly.io/docs/hands-on/install-flyctl/" >&2
  exit 1
fi

FLY_CMD="$(command -v fly || command -v flyctl)"

if [[ ! -f "fly.toml" ]]; then
  echo "fly.toml not found in $(pwd). Run this script from the repo root." >&2
  exit 1
fi

if [[ ! -f "Dockerfile" ]]; then
  echo "Dockerfile not found in $(pwd). Run this script from the repo root." >&2
  exit 1
fi

echo "==> Creating Fly app config from fly.toml"
"$FLY_CMD" launch --no-deploy --name "$APP_NAME" --region "$REGION" --copy-config --yes || true

echo "==> Creating the persistent volume: $VOLUME_NAME"
"$FLY_CMD" volumes create "$VOLUME_NAME" --size "$VOLUME_SIZE" --region "$REGION" --yes || true

echo "==> Setting deployment secrets"
SECRETS=("APP_PASSWORD=$APP_PASSWORD")
if [[ -n "$STATSPLUS_LEAGUE_URL" ]]; then
  SECRETS+=("STATSPLUS_LEAGUE_URL=$STATSPLUS_LEAGUE_URL")
fi
if [[ -n "$STATSPLUS_COOKIE" ]]; then
  SECRETS+=("STATSPLUS_COOKIE=$STATSPLUS_COOKIE")
fi
"$FLY_CMD" secrets set "${SECRETS[@]}"

echo "==> Pinning the machine count to 1 (budget guard)"
# With a single machine and auto_stop_machines/min_machines_running=0 in fly.toml,
# the app scales to zero when idle and can never fan out into extra billable VMs.
"$FLY_CMD" scale count 1 --app "$APP_NAME" --max-per-region 1 --yes || \
  "$FLY_CMD" scale count 1 --app "$APP_NAME" --yes || true

echo "==> Deploying application"
"$FLY_CMD" deploy

echo ""
echo "Deployment complete."
echo "Be sure to open the app and confirm the upload + ranking flow still works."
echo "If you use the StatsPlus integration, re-enter the cookie from the Settings page if it expires."
echo ""
echo "IMPORTANT budget backstop (one-time, not scripted):"
echo "  Dashboard -> your org -> Billing -> Spend limits -> set a hard monthly cap."
echo "  Verify guards with: $FLY_CMD scale show --app $APP_NAME   and   $FLY_CMD machine list --app $APP_NAME"
