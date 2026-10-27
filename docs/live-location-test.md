# iPhone location test — 28 October 2026

**Readiness: NO.** This report records checks run on 27 October. Browser fixture tests are not proof of live model execution or physical GPS.

## Code and environment

- Branch: `feature/context-notifications`, HEAD `7cefe20`.
- Cached `origin/main` matches HEAD. A read-only `git ls-remote` found newer remote main `842d50e9fac41a9abbc9e133e939c2f1a53bf5c0`. No fetch, merge, commit, push, deployment change, or database write was performed.
- Existing uncommitted frontend work remains present.
- Frontend API client uses `/backend` through the existing Vite proxy to `https://daffas-macbook-pro.tail612eba.ts.net:8443`.
- Existing private Tailscale Serve configuration forwards frontend HTTPS on port 443 to local Vite port 5176. It was inspected, not changed.

## Executed checks

| Check | Observed result |
| --- | --- |
| Tailscale on this Mac | Running, MagicDNS enabled |
| Daffa hostname DNS | Correct private IP `100.84.223.63` |
| Daffa peer | Absent from this Mac's current peer list |
| Daffa `:8443/health`, `/openapi.json`, `/notifications`, `/entities?domain=food`, `/open-loops` | Timed out; HTTP status and deployed commit unknown |
| Direct `http://100.84.223.63:8000/health` | Timed out |
| Frontend HTTPS `/context-simulator` | HTTP 200; Mac curl certificate verification result 0 |
| Frontend HTTPS `/backend/health` | Timed out, certificate verification result 0 |
| Python HTTPS trust | Local Python CA bundle cannot validate the frontend issuer; curl with the Mac trust store succeeds. No TLS verification was bypassed. |
| Local port 8000 | Sample-mode container, not the real test backend |
| Local port 8001 | Health reports real mode and `ZetarisRepository`; OpenAPI exposes notification routes, but GET `/notifications` returns 503 |
| Read-only JDBC | Connected using the existing Zetaris driver and installed Java 18; entity/evidence graph retrieved |
| Backend offline suite | 279 run, 273 passed, 6 skipped. Initial sandbox bind failures disappeared with permitted loopback access. |
| Frontend build/typecheck | Passed |
| Collection tests | 2 passed |
| Browser GPS/UI contracts | 7 passed with explicitly mocked GPS/API responses; no real API writes |

The local backend OpenAPI reports API version `0.1.0`, not a Git SHA. Its exact running commit cannot be established from that value. The unreachable Daffa backend version cannot be identified remotely during this check.

## Real saved data, local instance only

The read-only repository report is in `artifacts/live-location/zetaris-readiness.json`:

- 68 entities; 0 active Open Loops; 0 entities with explicitly verified coordinates and a coordinate source.
- OMB Burger: entity `ent_15c0bc1f7221`.
- Evidence `ev_911de93f16a233a77fcfc1cb`, original `IMG_8922.PNG`, non-sensitive.
- Persisted EvidenceEntity relationship: `depicted`, confidence 0.9.
- Location text: Melbourne CBD, Melbourne, Australia.
- No latitude, longitude, `location_verified`, or `location_source` metadata.
- No active linked Open Loop found. No current usable Open Loop ID can be supplied.

These are this Mac's configured Zetaris records, not a claim about Daffa's unavailable database. Historic proof files are not substituted for current reads.

## Required preparation with Daffa

Before changing his deployment, Daffa should inspect its checkout and process:

```sh
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --format='%h %s'
```

Agree which reviewed checkout will run. This work is uncommitted; Daffa's existing deployment does not automatically receive it. Do not blindly pull or restart over his uncommitted work.

On his backend host, compare local health/OpenAPI with private HTTPS:

```sh
curl --fail --max-time 15 http://127.0.0.1:8000/health
curl --fail --max-time 15 http://127.0.0.1:8000/openapi.json
curl --fail --max-time 30 http://127.0.0.1:8000/notifications
curl --fail --max-time 15 https://daffas-macbook-pro.tail612eba.ts.net:8443/health
```

The reviewed backend must register:

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/context-simulator/evaluate` | Shared SIMULATED/BROWSER evaluation and persisted decisions |
| GET | `/context/evaluations/{evaluation_id}` | Saved input, candidates, traces and result |
| GET | `/notifications` | Already approved notifications; no AI reasoning |
| GET | `/notifications/{notification_id}` | Notification and original evidence references |
| POST | `/notifications/{notification_id}/actions` | Delivery, read, dismissal and supported feedback |

GET on a POST-only route can return 405; this does not mean the route is missing. Verify OpenAPI methods before evaluating.

`/api/context/evaluate` and `/context/evaluate` are a different, read-only overlay API; they do not replace the persisted notification endpoint above.

Daffa must verify his actual repository can read/write the existing `context_evaluations` and `notifications` tables, plus context events. Local 503 has not been diagnosed as a specific missing table; do not assume a schema issue or create objects blindly. Existing schema dry-run: `backend/sql/context_notifications.sql`.

Select one non-sensitive stored restaurant/destination with a genuinely verified coordinate source. Persist latitude, longitude, `location_verified="true"`, and `location_source` in that entity's existing metadata through the repository after source verification. Preserve Evidence unchanged. Confirm its existing agent-produced Open Loop is OPEN or ACTIVE and linked to that entity. If no loop exists, use the established Open Loop workflow; do not manually fabricate an intention for this test.

Nightshift must be reachable with the configured reasoning model/provider receipts. Keep all credentials in ignored local environment files. This task changed no model IDs, prompts, orchestration, or repository contracts.

## Synthetic acceptance before walking

Only run after the saved entity's coordinates and active graph are verified. Use `backend/scripts/trigger_context.py` or the Context Simulator; both submit to the same service used by live GPS.

Prepare three test points using geodesic offsets from the verified entity: 100 m, 500 m, and more than 3 km. Record submitted coordinates, verified coordinates/source, computed Haversine distance, evaluation ID, run ID, Context/Critic traces and receipts, evidence IDs, delivery result and notification ID. These real-agent runs were **blocked**, not executed in this session.

Current geographic retrieval requires the entire GPS uncertainty radius to fit within the threshold: distance + accuracy ≤500 m is strong; ≤1000 m is moderate; otherwise distant. A 500 m point with 20 m accuracy is moderate. Text-only suburb matches do not qualify.

The Context Agent judges relevance; the Critic decides whether to interrupt. Existing bounded verification/revision branches remain intact. SURFACE is never guaranteed. Delivery additionally requires supported evidence, active loop, verified proximity and actual NVIDIA/Nemotron receipts.

Default cooldown is 21,600 seconds (6 h) per loop, using server time. Synthetic notifications can therefore suppress later live tests of the same loop. Do not reset or bypass user feedback to force a positive result. Inspect exclusions and plan the test timing. Replaying identical input returns the saved evaluation; fresh GPS IDs still respect cooldown. A distant or missing-candidate check may legitimately skip model calls and stay silent.

Confirm an actual SURFACE creates a persisted notice, the notification GET returns it, and the open frontend renders it. Open its Why now? view, then View saved intention and the original screenshot. Confirm STAY_SILENT creates no notice. Repeat to validate deduplication/cooldown without resetting data. Polling only reads notices and must not make new agent calls.

## iPhone checklist

1. Keep the frontend laptop, Daffa backend, Zetaris and Nightshift running and awake. Join the same tailnet from the iPhone and enable Tailscale.
2. Open **https://clarissas-macbook-pro.tail612eba.ts.net/context-simulator** in Safari. This URL serves the current local frontend; it is not usable away from home if that laptop or its upstream services are offline. First check **https://clarissas-macbook-pro.tail612eba.ts.net/backend/health** returns real mode. It timed out during this check.
3. Optional: Safari → Share → Add to Home Screen. Recheck location permission in the installed app; permission behavior on a physical iPhone is not yet verified.
4. Keep pingo open in the foreground and press **Check Nearby**. Grant location permission and enable Precise Location. This is one fresh fix per press, not background monitoring or automatic walking detection.
5. Check “Location received” and the reported accuracy/timestamp. Test around the verified saved place within 100–500 m, ideally with a small GPS uncertainty. **No verified visit destination is ready yet; do not use approximate OMB Burger coordinates.**
6. An evidence-backed ping appears at the top only if Context/Critic approve and delivery safeguards pass. Exact copy comes from the saved entity and approved reason; no promised notification text is hardcoded.
7. Scroll to Candidate intentions, Agent decisions, and Submitted context and trace identifiers. `source` should be BROWSER. Open an approved ping for Why now?, the saved intention, and screenshot provenance.
8. For STAY_SILENT, inspect exclusions: missing verified coordinates, no active graph, distance + accuracy, cooldown, snooze, terminal feedback, or an actual Context/Critic rejection. Silence is valid.
9. For permission denied, allow location for the site in Safari settings; verify iOS Location Services and precise-location access. For timeout/unavailable, move outdoors and retry. HTTP tailnet IP URLs are unsuitable for browser geolocation; use HTTPS.
10. For no banner, inspect the evaluation's final action and delivery reason, `/notifications`, read/dismissed state, cooldown and backend errors. Approval alone is not delivery. Existing read notices are not newly displayed. Keep the app visible; polling pauses in a hidden tab.

## What changed in this task

- `frontend/src/pages/context/ContextSimulator.tsx`: distinct GPS request, capture, evaluation, no-match, safe-failure and permission/network states; captured fix details; stale result cleared before a new fix.
- `frontend/tests/liveLocation.browser.mjs`: 7 browser contract scenarios with fixture-only GPS/API, including source/timestamp/accuracy and exclusion of staged simulation events. Requires Node 22+, Vite :5176 and a dedicated Chrome CDP :9333.
- This report and `artifacts/live-location/` results/screenshot.

Browser fixtures cover denied/unavailable/timeout, backend error, failed-safe, STAY_SILENT and SURFACE banner/link. Physical iPhone GPS, current live agents, real notification writes, deployed deduplication and phone-to-backend access remain unverified. Existing offline notification tests cover those service policies with explicitly scripted gateways and SQL test fixtures.
