# Pingo context simulation and in-app recalls

Implemented on `feature/context-notifications`. No agent prompts, model IDs,
LoopRepository signatures, RunResult/TraceEvent fields, or orchestrator branches
were changed. The existing Homepage and entity-detail visual files are unchanged.

## Current live verification

- Existing Lightning JDBC driver, Java 11 and `SELECT 1` succeeded.
- With explicit approval, added only `recall_data.app.context_evaluations` and
  `recall_data.app.notifications`. Both were read-verified. REST was not checked;
  this integration uses JDBC.
- A real synthetic-location ContextEvent and its `STAY_SILENT` evaluation were
  persisted to Zetaris, read back through HTTP, and replayed without another run.
- A synthetic calendar input used the same workflow and stayed silent with the
  Context Agent's existing no-active-candidates rule. No model receipt was claimed.
- The configured database currently contains **zero OPEN/ACTIVE loops** (one
  invalidated storage-fixture loop). It contains 31 Evidence rows including the
  earlier storage fixture; the 30 real screenshot Evidence records remain intact.
- Nightshift model discovery currently fails with the adapter's sanitized
  `Nightshift cannot be reached` error. No direct-provider fallback was used.
- Consequently, a live model-backed SURFACE, approved notification write/delivery,
  and mobile GPS relevance are **not yet verified**. Offline tests use explicitly
  scripted model fixtures; these are not production decisions or sponsor receipts.

## Start the current preview

The implementation preview uses backend **8001** and frontend **5176** to leave
other running services untouched. Open `http://127.0.0.1:5176/context-simulator`.

From the repository root:

```sh
export JAVA_HOME="$(/usr/libexec/java_home -v 11)"
PINGO_FRONTEND_ORIGINS=http://127.0.0.1:5176 \
backend/.venv/bin/python backend/scripts/serve.py \
  --env-file ../getting-started/.env.local --host 127.0.0.1 --port 8001
```

In a second terminal, with Node 22 installed:

```sh
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 5176
```

The real env file must set `SAMPLE_MODE=false` and the existing Zetaris and
Nightshift variables. Keep credentials in ignored local files. `SAMPLE_MODE=true`
still starts offline with the original sample flow; the simulator explicitly
rejects model evaluation in that mode rather than presenting fixtures as live AI.

For a fresh database, inspect the additive schema first:

```sh
backend/.venv/bin/python backend/scripts/setup_context_storage.py
# After the operator approves that dry-run:
backend/.venv/bin/python backend/scripts/setup_context_storage.py --apply \
  --env-file ../getting-started/.env.local
```

## Prepare actual intentions before the demo

When Nightshift is running, use the **existing** Open Loop processing script to
reason over already-stored Evidence, without repeating screenshot perception:

```sh
backend/.venv/bin/python backend/scripts/process_open_loops.py \
  --env-file ../getting-started/.env.local --env-file backend/.env.local --dry-run
backend/.venv/bin/python backend/scripts/process_open_loops.py \
  --env-file ../getting-started/.env.local --env-file backend/.env.local --limit 1
```

The existing private ledger handles resumability. The script and its prompts were
not changed. Inspect its actual result before processing more records. The Context
Simulator never creates an intention just to ensure a notification appears.

In the simulator:

1. Set the current time and IANA timezone. Enter a location, appointment or time
   event. The location defaults are clearly synthetic example input.
2. Press **Simulate Location / Calendar Event / Time** to stage the event. Staging
   makes no API or model calls. Calendar supports optional coordinates.
3. Press **Run Context Evaluation**. The server loads persisted active loops,
   linked entities and real Evidence, then calls the existing orchestrator.
4. Inspect candidates, concise Context/Critic summaries, real routing receipts,
   trace IDs and the unchanged RunResult. Repeating an identical request returns
   the persisted result without invoking models.
5. Only a final Critic **SURFACE**, with valid NVIDIA/Nemotron receipts, active
   loop and non-sensitive grounding, creates an approved recall. A STAY_SILENT,
   verification failure, unavailable model or ASK does not create a notification.
6. The open app polls every 15 seconds (pauses while hidden), and displays newly
   approved unread recalls. Open one to see the supporting screenshots, reason,
   entity links and existing `/entity/:loopId` intention details.
7. Repeat location inputs to demonstrate cooldown. **Next Location** evaluates
   each row of a coordinate sequence separately. **Reset Simulation** clears only
   the panel, not persisted events, feedback, intentions or cooldowns.

Simulation uses **real application state**. Pressing Done on a simulated recall
really resolves its underlying intention. Source labels remain visible everywhere.

## HTTP contract

All requests use the existing API base URL and centralized `services/api.ts`.

| Endpoint | Behaviour |
| --- | --- |
| `POST /context-simulator/evaluate` | Explicit model evaluation of location/calendar/time inputs |
| `GET /context/evaluations/{evaluation_id}` | Read saved result, including original traces; no model call |
| `GET /notifications` | Read approved active in-app recalls; no model call |
| `GET /notifications/{notification_id}` | Read an active recall's grounding and status |
| `POST /notifications/{notification_id}/actions` | Persist delivery/read/dismiss/user feedback |

Example simulation input (coordinates and appointment are synthetic):

```json
{
  "now": "2026-10-26T12:30:00+11:00",
  "events": [{
    "context_id": "ctx_example_001",
    "source": "SIMULATED",
    "type": "LOCATION",
    "timestamp": "2026-10-26T12:30:00+11:00",
    "timezone": "Australia/Melbourne",
    "location": {"latitude": -37.8, "longitude": 144.967, "accuracy_meters": 20}
  }]
}
```

Use a new context ID for a new observation. Reusing an ID with different content
is a 409 conflict. HTTP inputs reject naive timestamps, invalid coordinates,
nonfinite values, invalid calendar order, unsupported sources, and mixed simulated
and live observations. Calendar fields are `title`, `start_time`, `end_time`,
`location` and optional `description`; a TIME event needs the common fields.

## Canonical models and workflow

`context/contracts.py` adapts validated HTTP inputs into the existing ContextEvent
and ContextType. Source, timestamp, timezone, optional coordinates/accuracy,
calendar start/end and description are explicitly preserved in string metadata.
No source, geography or timezone information is silently treated as a live fact.
The existing Entity metadata carries verified place coordinates; no competing
agent model or new identity rules are introduced.

`ContextService` enriches events with deterministic distance diagnostics and a
no-inventory assertion, then injects a candidate repository view into the existing
`build_orchestrator(...).evaluate_context(...)`. Reads and writes still go through
the original repository. The orchestrator retains its one-retry limit, revision
branch, verification branch and safe outcomes. External source verification is
not configured: a request for verification stays silent.

No semantic appointment rules are implemented in the notification layer. Lunch,
shopping and trip relevance versus unrelated appointments are judgments made by
Context/Critic over the existing loop/entity graph and supplied event meaning.
A time tick also retrieves previously submitted calendar events in the same
simulation/live mode that have not ended and start within 14 days. It uses the
supplied timezone-aware clock, not the host's date. Calendar OAuth is not included.
The existing Context Agent's 30-candidate limit remains explicit in diagnostics.

ASK is preserved with its real question in the developer results. The current
Check-in schema only answers merge questions, so context questions are not forced
into that incompatible contract. No fabricated clarification or merge answer is
submitted.

## Geography

Haversine distances use only persisted entity metadata with:

```text
latitude, longitude
location_verified=true
location_source=<auditable verified source>
```

A shopping product additionally needs `location_role=store` and `store_name` to
identify an explicitly verified physical store relationship. No inventory
availability is inferred. The agent receives this limitation, and notification
copy makes no stock or walking-distance promise. Do not add these flags to an
unverified screenshot extraction merely to make it eligible.

The defaults are 500 m strong and 1000 m moderate. The GPS uncertainty radius is
added conservatively to distance. Beyond that radius a location-only event has no
proximity candidate. Suburb/city text without verified coordinates is reported as
unlocated, not converted to a fabricated point. Such entities can still be judged
semantically for calendar/time context. No geocoder, vector search, or location
metadata backfill was introduced.

Environment controls are documented in `backend/.env.example`:
`PINGO_NEARBY_STRONG_METERS`, `PINGO_NEARBY_MAX_METERS`,
`PINGO_NOTIFICATION_COOLDOWN_SECONDS` (21600), `PINGO_SNOOZE_SECONDS` (86400),
and `PINGO_FRONTEND_ORIGINS` for an explicit additional development origin.

## Notification state and feedback

`ContextEvaluation` and `Notification` are additional repository records in
`repositories/context_store.py`, separate from the unchanged LoopRepository.
Zetaris persists their JSON payloads plus stable IDs in the two additive tables;
the in-memory repository implements the same store methods for offline tests.
Existing `context_events` stores the original observations. No SQLite/file-based
production side database exists. Ingestion Evidence remains append-only.

- Evaluation ID hashes the complete validated request. A durable RUNNING record
  is written before model calls. A crash never silently re-executes that record:
  return 409 and require an explicit new context ID.
- Notification ID derives from the run ID. The same cited context event cannot
  notify the same loop again, even after cooldown.
- Repeated new GPS events are suppressed for the same loop for six **actual
  wall-clock** hours. A simulated time jump cannot bypass delivery cooldown.
- Approval is `APPROVED`. Only an explicit browser acknowledgement after render
  changes it to `DELIVERED`; read remains independent. This proves in-app render
  acknowledgement, not OS push, background delivery or human attention.
- `DONE` resolves the real loop; Evidence is retained.
- `SNOOZE` suppresses the loop for one actual day; the approved recall can reappear
  afterward. Polling does not reason again.
- `NOT_RELEVANT` and `JUST_INSPIRATION` persist terminal reminder suppression for
  the loop without inventing a new intention or adding unsupported LoopStatus.
- `DISMISS` hides this recall; `READ` marks it read. Terminal feedback is immutable;
  stale tabs cannot undo it. These are the explicitly implemented notification
  feedback semantics, separate from merge-question feedback.

Sensitive chains never enter the simulator candidate list or reasoning calls.
Delivery independently revalidates active status, cited context, real linked
Evidence, privacy and receipts. A SURFACE decision blocked by delivery safeguards
is kept intact in RunResult and shown with a separate delivery status.

Zetaris/JDBC still has no multi-table transactions. Existing compensation scopes
wrap final notification/evaluation and Done/feedback writes, never model calls.
Run **one backend worker**: the in-process evaluation lock and existing repository
compensation are not a distributed lock. Multi-worker/multi-host exactly-once
execution and recovery of uncertain JDBC writes remain outside MVP.

## Browser GPS and Tailscale

**Check Nearby** obtains one browser observation and posts source `BROWSER` through
the exact same evaluation path. It excludes staged simulation inputs. It handles
permission denial, timeout and unavailable positioning; it never calls watchPosition.

Geolocation requires permission and a secure context:
[MDN Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API).
An arbitrary `http://100.x.y.z:port` Tailscale IP is not sufficient. Use an HTTPS
same-origin frontend/API deployment, for example
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), which can
serve a local HTTP app over tailnet HTTPS. The existing nginx `/api` reverse proxy
is suitable. On the phone verify `window.isSecureContext === true`, permission,
reachable API and the configured backend services. Tailscale was not installed or
reconfigured by this task, and no mobile-device live result is claimed.

## Home Screen and laptop trigger demo

The frontend now includes an installable PWA manifest, Home Screen icons and a
small service worker for notification clicks. It deliberately does not cache API
data. On iPhone, connect Tailscale to the same tailnet and open
`https://clarissas-macbook-pro.tail612eba.ts.net/` in Safari. Choose
**Share → Add to Home Screen**, launch Pingo from its new icon, and press
**Turn on notifications**. The
permission is requested only from that button. When the app is open, it polls
persisted approved notifications and can show both the in-app recall and an iOS
system notification. Polling never invokes an agent.

This first demo requires Pingo to remain open or active. Reliable delivery while
the app is fully closed requires Web Push subscriptions and VAPID delivery; those
are not represented as working by this implementation.

From a laptop, send synthetic context with `backend/scripts/trigger_context.py`.
The script only submits observations and prints the resulting trace. It does not
choose a decision itself:

```sh
export PINGO_API_BASE_URL=https://backend-device.tailnet.ts.net:8443

backend/.venv/bin/python backend/scripts/trigger_context.py location \
  --latitude -37.8000 --longitude 144.9670 --accuracy 20 --label Carlton

backend/.venv/bin/python backend/scripts/trigger_context.py calendar \
  --title "Lunch with Sarah" \
  --start "2026-11-02T12:30:00+11:00" \
  --end "2026-11-02T14:00:00+11:00" \
  --location Carlton --city Melbourne --country Australia \
  --description "Catch-up lunch"

backend/.venv/bin/python backend/scripts/trigger_context.py time \
  --at "2026-11-01T12:30:00+11:00" --label "One day before the trip"
```

For these triggers, Context Agent loads active loops and linked entities and
judges contextual relevance. Critic Agent decides SURFACE, STAY_SILENT, ASK,
VERIFY_CONTEXT or REQUEST_REVISION. Open Loop Agent runs only for an actual
revision branch. Evidence Agent does not run because the Evidence is already in
Zetaris. Only a receipt-verified Critic SURFACE can create a notification.

## Validation

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests -v
cd frontend && npm run build
```

The new offline suite exercises scenarios A–J through the actual Context/Critic
parsers and orchestrator with **scripted test gateways**, plus receipt rejection,
source/time validation, sensitive-data exclusion, ASK/verification, replay across
service restart, no model calls from polling, feedback and SQL write compensation.
The SQL harness is explicitly not a live Zetaris claim.

Desktop/mobile browser checks cover 320/390/768/1440 px, staging, calendar timezone
conversion, time input, stable IDs on retry and notification details/actions.
Notification presentation uses labeled browser-test fixtures only. The real
JDBC/API proof is the stored silent evaluation described above. The full live
approved-notification demo awaits deployment of these stateful routes alongside
working Nightshift and genuine active loops.

Final checks: 248 backend tests ran, 246 passed and two explicitly opted-in live
integration tests were skipped. The 29 focused context/trigger tests passed.
TypeScript and the production frontend build passed after the notification/PWA
changes; a later shell lacked the project's Node/npm toolchain, so it did not
replace that successful build result.

## File inventory

New backend files:

- `app/context/contracts.py`, `geography.py`, `service.py`, `routes.py`
- `app/repositories/context_store.py`
- `sql/context_notifications.sql`
- `scripts/setup_context_storage.py`, `scripts/trigger_context.py`
- `tests/test_context_notifications.py`, `tests/test_trigger_context.py`
- This implementation and demo report

Modified backend files: `app/main.py`, `app/repositories/memory.py`,
`app/repositories/zetaris.py`, `.env.example`.

New frontend files:

- `pages/context/ContextSimulator.tsx`, `contextTime.ts`, `context.css`
- `features/notifications/NotificationCenter.tsx`, `NotificationDetail.tsx`,
  `NotificationSetup.tsx`, `systemNotifications.ts`, `notifications.css`
- `public/manifest.webmanifest`, `public/service-worker.js`, `public/pwa/*`

Modified frontend files: `services/api.ts`, `router/AppRouter.tsx`,
`components/layout/AppShell.tsx` (route access and delivery mounting only).

No dependencies, existing prompts, agent files, orchestrator logic, domain models,
agent repository protocol, screenshot JSON or Home/entity visual files were changed.
