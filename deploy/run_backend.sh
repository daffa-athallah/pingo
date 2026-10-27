#!/bin/bash
# Started by launchd (com.recall.backend). Waits for Zetaris, then runs the API in the foreground so launchd can restart it if it dies.
# JAVA_HOME and the Zetaris/Nightshift settings come from env.local and backend/.env (read by serve.py); nothing secret lives here.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONUNBUFFERED=1
# Any *.ts.net origin may call the API (tailnet only: `tailscale serve`, never Funnel). Override by exporting your own value.
export RECALL_CORS_ORIGIN_REGEX="${RECALL_CORS_ORIGIN_REGEX:-https://.*\.ts\.net(:[0-9]+)?}"
# The Meterless H-MEM memory engine (engines/hmem, started by com.recall.hmem). Without it the backend still runs and reports memory as unavailable.
export RECALL_HMEM_URL="${RECALL_HMEM_URL:-http://127.0.0.1:8300}"
# Nearby reminders: once a loop has pinged, wait this long before it can ping again (the code default is 6 h). Short enough that walking away and coming back
# pings again in a demo. Radius is set below.
export PINGO_NOTIFICATION_COOLDOWN_SECONDS="${PINGO_NOTIFICATION_COOLDOWN_SECONDS:-120}"
# Reach: a place only counts as "nearby" when distance plus GPS uncertainty is within this many metres. Beyond it nothing is asked and nothing is sent.
export PINGO_NEARBY_STRONG_METERS="${PINGO_NEARBY_STRONG_METERS:-200}"
export PINGO_NEARBY_MAX_METERS="${PINGO_NEARBY_MAX_METERS:-200}"
until /usr/bin/nc -z localhost 10000 2>/dev/null; do
  echo "$(date '+%F %T') waiting for Zetaris on :10000 (colima start; docker compose up -d)"; sleep 5
done
cd "$ROOT"
echo "$(date '+%F %T') starting Recall API on :8000"
exec "$ROOT/backend/.venv/bin/python" backend/scripts/serve.py --env-file env.local --env-file backend/.env --port 8000
