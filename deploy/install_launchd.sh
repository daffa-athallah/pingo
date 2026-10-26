#!/bin/bash
# Install, remove or inspect Recall's launchd jobs (user level; no sudo).
#   deploy/install_launchd.sh install     backend auto-start/restart, sleep prevention, Colima at login, daily Check-in job (06:00)
#   deploy/install_launchd.sh uninstall   stop and remove all four
#   deploy/install_launchd.sh status
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABELS="com.recall.hmem com.recall.backend com.recall.caffeinate com.recall.colima com.recall.daily-checkins"
DOMAIN="gui/$(id -u)"

# bootout is asynchronous: wait until the old job is really gone before loading the new one, and retry the load.
unload() {
  launchctl bootout "$DOMAIN/$1" 2>/dev/null || true
  for _ in $(seq 1 40); do launchctl print "$DOMAIN/$1" >/dev/null 2>&1 || return 0; sleep 0.5; done
}
load() {
  for _ in 1 2 3 4 5 6; do launchctl bootstrap "$DOMAIN" "$AGENTS/$1.plist" 2>/dev/null && return 0; sleep 1; done
  return 1
}

case "${1:-}" in
  install)
    if /usr/sbin/lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl list | grep -q com.recall.backend; then
      echo "Port 8000 is already used by a manually started backend. Stop it first (see: lsof -nP -iTCP:8000 -sTCP:LISTEN), then rerun."; exit 1
    fi
    mkdir -p "$AGENTS" "$HOME/Library/Logs/recall"
    for label in $LABELS; do
      sed -e "s#{{ROOT}}#$ROOT#g" -e "s#{{HOME}}#$HOME#g" "$ROOT/deploy/launchd/$label.plist.template" > "$AGENTS/$label.plist"
      unload "$label"
      if load "$label"; then echo "installed $label"; else echo "FAILED to load $label"; failed=1; fi
    done
    [ "${failed:-0}" = 1 ] && { echo "Some jobs failed to load; rerun, or check: launchctl print $DOMAIN/<label>"; exit 1; }
    echo "Logs: ~/Library/Logs/recall/   Check everything: backend/.venv/bin/python backend/scripts/preflight.py"
    ;;
  uninstall)
    for label in $LABELS; do
      unload "$label"
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
