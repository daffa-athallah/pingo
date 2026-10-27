# Running the real app on a phone (tailnet only)

Everything is private to your Tailscale network. Nothing is exposed publicly (no Funnel).

| What | URL |
| --- | --- |
| App (open this on the phone, Safari) | https://daffas-macbook-pro.tail612eba.ts.net/ |
| API (the app talks to it) | https://daffas-macbook-pro.tail612eba.ts.net:8443 |

The phone needs HTTPS for GPS, so use these URLs, not an IP address or `http://`. The Mac must stay awake and on power, with Colima, Zetaris, Nightshift and Tailscale running (`backend/scripts/preflight.py` checks them).

## Start (Mac)

```sh
# API: runs under launchd (com.recall.backend). Restart it after pulling new code:
launchctl kickstart -k gui/$(id -u)/com.recall.backend
# App: build once, then serve it
cd frontend
HOST=daffas-macbook-pro.tail612eba.ts.net
VITE_API_BASE_URL=https://$HOST:8443 VITE_CHECKIN_DEMO=false npx vite build
VITE_DEV_ALLOWED_HOST=$HOST VITE_API_BASE_URL=https://$HOST:8443 npx vite preview --port 5175 --host 127.0.0.1
# Publish the app on the tailnet
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --https=443 http://127.0.0.1:5175
```

## Add a real screenshot (agents → Zetaris, models through Nightshift)

1. Home → **+ Add screenshot**, tick the confirmation (this is your real, permanent history), choose the screenshot.
2. The agents run and their steps appear: Evidence, memory, Open Loop, then **Location**: the place is looked up on OpenStreetMap and accepted only on an unambiguous match (name and suburb).
3. If the map has no match (small shops often are missing), the page asks for a pin: paste a Google Maps share link or `latitude, longitude` and tap **Save location**. A person's own pin is a verified source.

A place with no verified coordinate is never matched by distance. Nothing is guessed.

## Test nearby on the phone

1. Open **Developer: Context Simulator** (bottom of Home) → **Real agent evaluation** → **Check Nearby**, allow location (Precise).
2. Within about 500 m of a located place, the Context Agent and Critic decide. A reminder appears as a Pingo banner; otherwise the page says why it stayed silent. A reminder for the same intention is limited to once every 6 hours.
3. Manual option from the Mac: `backend/scripts/set_entity_location.py` (dry run by default).
