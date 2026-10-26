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

Response (every field of the earlier contract is kept; `decision`, `provenance`, `workspace`, `events`, `message` and `status` are additions):

```json
{
  "run_id": "run_…",
  "status": "done",
  "decision": "SURFACE",
  "final_action": "SURFACE",
  "provenance": "live",
  "workspace": "canonical",
  "synthetic": true,
  "events": [{"context_id": "ctx_…", "context_type": "CALENDAR", "title": "Dinner with Alex", "occurs_at": "…", "location_name": "Fitzroy North", "city": "Melbourne", "evaluated": true}],
  "message": {"kind": "SURFACE", "title": "Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)", "body": "Calendar dinner in Fitzroy North tomorrow matches active interest in …"},
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

`decision` (same value as `final_action`; STAY_SILENT is the restraint outcome) is one of:

| Value | What the UI does |
| --- | --- |
| `SURFACE` | Show the notification-style card from `surface`; the **Why now?** screen is `why_now`, `evidence`, `context` and `receipts` |
| `STAY_SILENT` | Show nothing (or a quiet "nothing relevant" in a debug view). This is the normal outcome |
| `ASK` | Show `ask.question` as a Check-in prompt |
| `FAILED_SAFE` | Treat as silent; `error` is a safe message |

Guarantees:

- **Read-only.** An evaluation never changes stored loops, Evidence or Check-ins. If the Critic asks for a loop revision, the trace shows it and the change is discarded afterwards.
- **Privacy gate.** Events whose title or place looks private (health, money, legal and similar, English and Indonesian) are dropped locally before any model sees them and listed in `skipped_events` without their title. It is a word list, not a classifier.
- `message` is ready to show: the loop's short name and the Critic's own reason. No extra model call writes it. It is `null` unless the decision is `SURFACE` or `ASK`.
- `provenance` says who answered: `live` (real models), `scripted` (the credential-free sample fixture; never present it as a real decision), `recorded` (reserved). `workspace` says which data it ran on: `canonical`, `demo` or `sample`.
- Each run is saved (`GET /api/runs/{run_id}`) and can be opened in Agent Activity via `GET /agent-events/{run_id}`.
- Errors: `422` invalid request, `503` model gateway unavailable (the message is safe, no provider output).

## Saving a screenshot (asynchronous, observable)

`POST /api/screenshots` takes the **raw image bytes** as the body (PNG, JPEG or WebP, at most 20 MiB; the type is decided from the bytes, not the filename). From a browser: `fetch(base + '/api/screenshots', {method: 'POST', body: file, headers: {'Content-Type': file.type}})`. No multipart.

It returns **`202` with a `run_id` at once**, then the real work (a vision call, then a reasoning call, about 15 to 40 seconds) runs in the background. Poll `GET /api/runs/{run_id}` about once a second: `status` is `running`, then `done` or `failed`, and `result.trace_events` grows while it runs, so the screen can show progress instead of freezing.

```json
{ "run_id": "run_…", "status": "running", "provenance": "live", "workspace": "demo", "status_url": "/api/runs/run_…" }
```

`GET /api/runs/{run_id}` (the same record is an item of `GET /runs`):

```json
{
  "run_id": "run_…", "kind": "screenshot_upload", "provenance": "live", "workspace": "demo", "status": "done",
  "synthetic_inputs": false, "started_at": "…", "finished_at": "…",
  "result": { "run_type": "EVIDENCE_INGESTION", "final_action": "STORED", "loop_id": "loop_…", "evidence_id": "ev_…", "error": null,
              "trace_events": [ "…see below…" ] },
  "outcome": {
    "status": "stored",
    "evidence": {"evidence_id": "ev_…", "sensitive": false, "domain": "food", "summary": "…", "entities": [{"entity_id": "…", "name": "Elmo's Hamburger"}], "image_url": "/evidence/ev_…/image"},
    "open_loop": {"decision": "ATTACH", "confidence": 0.85, "reason": "New screenshot about Elmo's Hamburger Restaurant directly supports the existing loop.",
                  "loop": {"loop_id": "loop_…", "title": "Interested in Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)", "screenshot_count": 4},
                  "change": {"change": "supporting screenshots 3 → 4", "before": {"screenshots": 3}, "after": {"screenshots": 4}}},
    "receipts": [{"agent": "EVIDENCE", "action": "EXTRACT", "receipt": {"routed_model": "gpt-4o-mini", "provider": "openai"}},
                 {"agent": "OPEN_LOOP", "action": "ATTACH", "receipt": {"routed_model": "nvidia/nemotron-3-ultra-550b-a55b", "provider": "nvidia"}}],
    "error": null
  }
}
```

`outcome` appears when the run is done. `?wait=1` on the POST waits and returns the finished record instead of `202` (scripts and tests).

### Events (what a run exposes)

Each `trace_events[]` item: `seq`, `timestamp`, `agent`, `action`, `reason`, `input_refs`, `next_step`, `output_ref`, `receipt` (sanitized `requested_model`/`routed_model`/`provider`, or `null`) and `detail` (structured, below). Only structured inputs, retrievals, decisions, receipts, confidences and state changes are exposed. **Model reasoning is never requested, stored or shown.**

| `agent:action` | `detail` |
| --- | --- |
| `UPLOAD:RECEIVED` / `QUEUED` / `DUPLICATE` | bytes, type, hash prefix; for a duplicate, `duplicate_of` |
| `EVIDENCE:STARTED` | `model` |
| `EVIDENCE:EXTRACT` | `domain`, `summary`, `confidence`, `entities[]` (name, type, brand, location, attributes). Sensitive: only `{sensitive: true}` |
| `ZETARIS:STORE` or `REPOSITORY:STORE` | `evidence_id`, `entities_new`, `entities_matched_existing` (and their names), `links`, `backend` |
| `OPEN_LOOP:RETRIEVE` | `related_evidence[]` (id, domain, summary snippet), `related_entities[]`, `candidate_loops[]` (id, title, status, entity names). This is exactly what the Open Loop Agent was given |
| `OPEN_LOOP:DECIDING` | `model`, counts |
| `OPEN_LOOP:<CREATE\|ATTACH\|REVISE\|RESOLVE\|IGNORE\|LEAVE_UNRESOLVED>` | `decision`, `target_loop_id`, `proposed_title`, `confidence`, `supporting_evidence_ids`, `supporting_entity_ids`, `material_uncertainty`, plus the reason |
| `OPEN_LOOP:STATE` | `change`, `before`, `after` (title, status, confidence, supporting screenshot count) |
| `RUN:DONE` / `FAILED_SAFE` | the final status line |

Storage is labelled for what it is: `ZETARIS` only when the repository really is Zetaris; in the demo workspace it is `REPOSITORY` with `backend: "in-memory demo workspace"`.

- `status` of `outcome`: `stored`; `stored_without_loop` (Evidence saved, the loop step failed safely, see `error`); `duplicate` (the same image was saved before: no model call, no second record).
- **Sensitive screenshots** (credentials, payment or ID numbers, health or private messages): the Evidence is kept, but `evidence` is `{sensitive: true}` only with no description or entities, no retrieval is shown and no reasoning model sees it (`OPEN_LOOP:IGNORE`), the trace does not name its content, and the image file is deleted. Show a neutral "saved, not analysed" message.
- The image is sent to the vision model through Nightshift (OpenAI GPT-4o-mini), as every screenshot is.
- Uploads are processed one at a time (Zetaris is single-writer); a second upload shows `UPLOAD:QUEUED` and waits.
- Errors: `400` empty body, `413` too large, `415` not PNG/JPEG/WebP, `501` sample mode. A run that fails ends with `status: "failed"`, a safe `error`, and nothing stored (`?wait=1` maps it to `502`, or `503` when the model gateway is unavailable).
- Uploaded images are served by `GET /evidence/{id}/image` like the imported ones.

## Runs, provenance and workspaces

`GET /runs` lists the runs of the **active workspace only**, newest first (each item has the shape above, with events). Another mode's runs are never listed, and `GET /integration-status.saved_reasoning_runs` follows the same rule.

| Field | Values |
| --- | --- |
| `provenance` | `live` real models answered; `scripted` the credential-free sample fixture answered; `recorded` reserved for a replayed real run |
| `workspace` | `canonical` real Zetaris data; `demo` the resettable in-memory demo workspace; `sample` the offline fixture |
| `synthetic_inputs` | `true` when the inputs (calendar events, test images) are demo input |

Never label `scripted` or `illustration` activity as a real run. The sample backend lists one `scripted` run; the frontend's hand-written traces are `illustration`.

`GET /health` reports `mode`, `workspace` and, in the demo workspace, `demo_workspace` (storage, snapshot counts).

## Demo workspace (for recording a live demo)

`backend/scripts/serve.py --demo` (port 8100) runs the real agents and real models over an **in-memory copy of the saved history** (30 Evidence, 65 entities, 69 links, 17 loops, from `backend/demo/snapshot.json`). Nothing is written to Zetaris. `POST /api/demo/reset` restores the snapshot and forgets the workspace's runs and uploads (demo only; `404` elsewhere). The frontend page `/demo` uploads a screenshot and shows the run live.

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
