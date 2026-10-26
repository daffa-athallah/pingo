#!/bin/bash
# Install, remove or inspect Recall's launchd jobs (user level; no sudo).
#   deploy/install_launchd.sh install     backend auto-start/restart, sleep prevention, Colima at login, daily Check-in job (06:00)
#   deploy/install_launchd.sh uninstall   stop and remove all four
#   deploy/install_launchd.sh status
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS="com.recall.backend com.recall.caffeinate com.recall.colima com.recall.daily-checkins"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  install)
    if /usr/sbin/lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl list | grep -q com.recall.backend; then
      echo "Port 8000 is already used by a manually started backend. Stop it first (see: lsof -nP -iTCP:8000 -sTCP:LISTEN), then rerun."; exit 1
    fi
    mkdir -p "$AGENTS" "$HOME/Library/Logs/recall"
    for label in $LABELS; do
      sed -e "s#{{ROOT}}#$ROOT#g" -e "s#{{HOME}}#$HOME#g" "$ROOT/deploy/launchd/$label.plist.template" > "$AGENTS/$label.plist"
      launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
      launchctl bootstrap "$DOMAIN" "$AGENTS/$label.plist"
      echo "installed $label"
    done
    echo "Logs: ~/Library/Logs/recall/   Check everything: backend/.venv/bin/python backend/scripts/preflight.py"
    ;;
  uninstall)
    for label in $LABELS; do
      launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
      rm -f "$AGENTS/$label.plist"
      echo "removed $label"
    done
    ;;
  status)
    for label in $LABELS; do
      if launchctl list | grep -q "$label"; then echo "loaded   $label  $(launchctl list | grep "$label" | awk '{print "pid="$1" last-exit="$2}')"; else echo "missing  $label"; fi
    done
    ;;
  *) echo "usage: $0 install|uninstall|status"; exit 2 ;;
esac
