# Running the demo machine

The backend, Zetaris and Nightshift all run on one Mac. This page is how to keep that Mac demo-ready.

## Before a demo

```sh
backend/.venv/bin/python backend/scripts/preflight.py --model
```

It prints PASS / WARN / FAIL for Colima, the Zetaris containers and data, Nightshift and the Nemotron route, the API, Tailscale (and that no Funnel exposes it publicly), the auto-start jobs and sleep prevention, and the fix for anything that fails. `--model` makes one tiny real model call; `--quick` skips the Zetaris and model checks. Exit code 1 means not ready.

## What starts by itself

`deploy/install_launchd.sh install` (no sudo; `uninstall` removes everything, `status` lists the jobs) sets up four user-level launchd jobs:

| Job | What it does |
| --- | --- |
| `com.recall.backend` | Runs the API on :8000 from `deploy/run_backend.sh`: waits for Zetaris, restarts within about 10 s if it dies, starts at login. Log: `~/Library/Logs/recall/backend.log` |
| `com.recall.caffeinate` | `caffeinate -ims`: stops idle sleep, including on battery |
| `com.recall.colima` | Starts Colima at login. The Zetaris containers have `restart: unless-stopped`, so they follow |
| `com.recall.daily-checkins` | Runs `daily_check_ins.py` at 06:00 local time (the Critic reviews look-alike loops and files today's Check-in questions) |

Not automated, on purpose or because it cannot be: the **Nightshift M1-M4 app** (add it under System Settings → General → Login Items), and Tailscale (starts at login by default; the `tailscale serve` setting persists).

## Recording the live demo (resettable workspace)

The canonical Zetaris is append-only, so a demo that uploads screenshots there can never be undone. Record against the demo workspace instead:

```sh
backend/.venv/bin/python backend/scripts/serve.py --demo          # port 8100; loads only backend/.env (Nightshift), no Zetaris
curl -X POST localhost:8100/api/demo/reset                         # back to the saved history (30 Evidence, 17 loops)
backend/.venv/bin/python backend/scripts/upload_e2e.py             # acceptance run: three synthetic images, live progress printed
```

Point the frontend at it with `VITE_API_BASE_URL=http://localhost:8100` and open `/demo`. Real models answer every call; only the storage is in memory, and the UI says so (`REPOSITORY` / "Demo workspace", never "Zetaris"). Refresh the snapshot from canonical Zetaris with `backend/scripts/export_snapshot.py` (read-only).

## Limits

- Closing the lid sleeps the Mac whatever `caffeinate` says, unless an external display is attached. Keep the lid open.
- `caffeinate -s` only holds on AC power. Plug in; preflight warns when on battery.
- Run one writer at a time: the API, `daily_check_ins.py` and `process_open_loops.py` all write to Zetaris, which has no multi-process coordination.
- The API has no authentication. Keep it on the tailnet (`tailscale serve`); never `tailscale funnel`. Preflight fails if a Funnel is on.

## Restarting by hand

```sh
launchctl kickstart -k gui/$(id -u)/com.recall.backend      # restart the API
tailscale serve --bg --https=8443 http://localhost:8000      # re-publish on the tailnet
colima start && (cd zetaris-platform && docker compose up -d) # Zetaris
```
