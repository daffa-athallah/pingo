# Backend API contract

For the UI. Base URL: `http://localhost:8000` locally, or the HTTPS URL you serve it on (see [Phone access](#phone-access-tailscale)). JSON everywhere, no authentication yet. Run it with `backend/scripts/serve.py`; see the root README.

Every response is real data from Zetaris unless a field says `synthetic`. In `SAMPLE_MODE=true` the same endpoints answer from labelled offline fixtures (no Zetaris, no model), which is the easiest way to build UI without the backend machine.

## Reading data

| Endpoint | Returns |
| --- | --- |
| `GET /health` | `{status, mode: "real"\|"sample", repository}` |
| `GET /integration-status` | `{zetaris: {connected, evidence, entities, open_loops} \| null, saved_reasoning_runs, ...}`. `zetaris` is live counts in real mode, `null` in sample mode |
| `GET /open-loops?domain=food\|shopping\|travel` | Active Open Loops, newest first (below) |
| `GET /open-loops/{loop_id}` | One loop, or 404 |
| `GET /evidence/{evidence_id}/image?w=600` | JPEG of the supporting screenshot, scaled to `w` px (128 to 1600). 404 for sensitive or missing Evidence |
| `GET /entities?domain=`, `GET /entities/{id}` | Entities with `screenshot_count` and `inferred_intention` |
| `GET /runs` | Saved real runs (full `RunResult`): `A_relevant`, `B_restraint`, `revision`. Inputs are labelled `synthetic_context` |
| `GET /agent-events/{run_id}` | `TraceEvent[]` for any saved or live run |

An Open Loop is a **hypothesis**, not a confirmed goal. Show it as such.

```json
{
  "loop_id": "loop_62822173fdc0",
  "title": "Interested in Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)",
  "domain": "food", "status": "ACTIVE", "confidence": 0.85, "location": "Melbourne",
  "entities": [{"entity_id": "ent_…", "name": "Elmo's Hamburger Restaurant"}],
  "screenshot_count": 3,
  "screenshots": [{"evidence_id": "ev_…", "summary": "…", "timestamp": "…", "image_url": "/evidence/ev_…/image"}]
}
```

`image_url` is relative: prefix it with the base URL and add `?w=`.

## Evaluating context ("why now")

`POST /api/context/evaluate` runs Context, then Critic (with the bounded revision and verification branches) for what the device reports. One call takes **about 30 to 40 seconds** (real model calls through Nightshift), so show a loading state.

```json
{
  "synthetic": true,
  "events": [{"context_type": "CALENDAR", "title": "Dinner with Alex",
              "occurs_at": "2026-10-27T19:00:00+11:00", "location_name": "Fitzroy North", "city": "Melbourne"}]
}
```

- `context_type`: `CALENDAR`, `LOCATION` or `TIME`. (`REAL_WORLD_EVENT` is not supported.) 1 to 5 events. Only these fields are sent to the model.
- `synthetic`: a **label** you set to `true` for demo or test input and `false` for real device data. Keep it visible in the UI. It does not change behaviour.
- Browser geolocation gives coordinates, not a place name. Send a human-readable `location_name`/`city` (for example from your own reverse lookup); the model reasons over names, not coordinates. Any extra field, such as latitude/longitude, is ignored and never stored or sent to a model.

Response:

```json
{
  "run_id": "run_…",
  "final_action": "SURFACE",
  "synthetic": true,
  "surface": {
    "loop": {"loop_id": "…", "title": "…", "domain": "food", "status": "ACTIVE", "confidence": 0.85},
    "entities": [{"entity_id": "…", "name": "…"}],
    "why_now": "Calendar dinner in Fitzroy North tomorrow matches active interest in …",
    "evidence": [{"evidence_id": "ev_…", "summary": "…", "timestamp": "…", "image_url": "/evidence/ev_…/image"}],
    "context": [{"context_id": "ctx_…", "context_type": "CALENDAR", "title": "Dinner with Alex", "occurs_at": "…", "location_name": "…", "city": "…"}]
  },
  "ask": null,
  "skipped_events": [],
  "receipts": [{"agent": "CRITIC", "action": "SURFACE", "receipt": {"requested_model": "…", "routed_model": "…", "provider": "nvidia"}}],
  "error": null,
  "result": { "…": "full RunResult with trace_events for the Agent Activity view" }
}
```

`final_action` is one of:

| Value | What the UI does |
| --- | --- |
| `SURFACE` | Show the notification-style card from `surface`; the **Why now?** screen is `why_now`, `evidence`, `context` and `receipts` |
| `STAY_SILENT` | Show nothing (or a quiet "nothing relevant" in a debug view). This is the normal outcome |
| `ASK` | Show `ask.question` as a Check-in prompt |
| `FAILED_SAFE` | Treat as silent; `error` is a safe message |

Guarantees:

- **Read-only.** An evaluation never changes stored loops, Evidence or Check-ins. If the Critic asks for a loop revision, the trace shows it and the change is discarded afterwards.
- **Privacy gate.** Events whose title or place looks private (health, money, legal and similar, English and Indonesian) are dropped locally before any model sees them and listed in `skipped_events` without their title. It is a word list, not a classifier.
- Each run is saved (`GET /api/runs/{run_id}`) and can be opened in Agent Activity via `GET /agent-events/{run_id}`.
- Errors: `422` invalid request, `503` model gateway unavailable (the message is safe, no provider output).

## Check-in (daily)

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/check-ins` | `{questions: CheckInQuestion[]}`: **today's** unanswered questions only. An unanswered question does not carry over; the next day starts fresh |
| `POST /api/check-ins/{id}/respond` | Body `{response, comment?}` (`comment` at most 500 chars). Responses: `same`, `different`, `related`, `other`. `200 {ok: true}`; `404` unknown; `409` already answered differently; `422` unknown response |

Questions today are "are these two the same thing?" from the Critic's duplicate review. `same` merges the two loops; every other answer leaves both alone. Supporting images are absolute URLs of the two loops' screenshots. The question shape matches `frontend/src/pages/checkin/checkInTypes.ts`. Questions are generated by `backend/scripts/daily_check_ins.py` (run it once a day); on a day with no look-alikes the list is empty.

## Phone access (Tailscale)

Browser geolocation only works on HTTPS (or localhost), so serve the UI and the API over HTTPS.

1. Both people, and the phone that runs the demo, install Tailscale and join the same tailnet.
2. The backend machine serves the API over HTTPS, for example `tailscale serve --bg --https=8443 http://localhost:8000` (flags differ between versions; check `tailscale serve --help`).
3. Allow the UI's origin on the backend by setting env vars before starting it:
   - `RECALL_CORS_ORIGINS=https://ica-mac.<tailnet>.ts.net:5173` (comma separated), or
   - `RECALL_CORS_ORIGIN_REGEX='https://.*\.ts\.net(:\d+)?'` to accept any tailnet host.
4. Point the frontend at it: `VITE_API_BASE_URL=https://<backend-machine>.<tailnet>.ts.net:8443`.

`tailscale funnel` would make the API public. There is no authentication, and the API serves personal screenshots and loops, so do not leave it on.

Without the backend machine: run the backend with `SAMPLE_MODE=true` (offline fixtures), or the frontend with `VITE_USE_MOCK=true`.
