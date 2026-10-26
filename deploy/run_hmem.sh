#!/bin/bash
# Started by launchd (com.recall.hmem): the Meterless H-MEM engine for the canonical workspace. Persistent, loopback only.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/backend/runtime/hmem"
cd "$ROOT/engines/hmem"
[ -x ./node_modules/.bin/tsx ] || { echo "missing tsx: run (cd engines/hmem && npm ci --ignore-scripts)"; exit 1; }
echo "$(date '+%F %T') starting H-MEM on 127.0.0.1:${HMEM_PORT:-8300}"
HMEM_PORT="${HMEM_PORT:-8300}" HMEM_PERSIST_DIR="$ROOT/backend/runtime/hmem" exec ./node_modules/.bin/tsx server.ts
