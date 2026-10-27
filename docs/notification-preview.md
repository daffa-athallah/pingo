# Notification preview and synthetic context testing

Implemented on `feature/context-notifications`. Existing uncommitted work was preserved. No reset, merge, commit, push, schema change, repository change, agent prompt change, model-routing change, or deployment change was performed. The real evaluations described below intentionally persisted synthetic context, decisions and one approved notification through the existing backend.

## Try it now

Open **http://127.0.0.1:5176/context-simulator** on this Mac, or **https://clarissas-macbook-pro.tail612eba.ts.net/context-simulator** through the existing private Tailscale frontend while this laptop/Vite is running.

1. Leave **Visual preview** selected.
2. Choose **Restaurant nearby**, **Upcoming lunch**, or **Shopping nearby**.
3. Choose **Preview in-app notification** or **Preview iPhone-style notification**.
4. Press **Preview notification**. Tap it for a clearly labelled example detail, or use its X / **Close preview**.

Examples are local React state. They have no record IDs, model calls, database writes, delivery acknowledgements or permission prompts. Preview interactions were tested while every backend response in the browser harness returned 503. The application-wide Check-in provider can still make its usual initial read when the app boots; preview does not depend on that response. Notification polling is not mounted in visual-preview mode, so preview actions do not poll Zetaris or acknowledge real notices.

`/dev/notifications` also opens the local examples in development. The earlier read-only replay remains available at `/dev/notifications?saved=true`; this optional replay reads stored content and therefore requires the backend.

## Separate real evaluation mode

Choose **Real agent evaluation**, or open `/context-simulator?mode=agents`.

- Enter location coordinates, accuracy and the evaluation timestamp, then **Simulate Location** to stage the event.
- For calendar, enter title, start/end, location, city and description, then **Simulate Calendar Event**.
- Press **Run agent evaluation** to POST the staged events to `/context-simulator/evaluate`.
- Observe submitted context, geographic retrieval diagnostics, matching intentions, Context/Critic decisions, delivery outcome, actual receipts and trace IDs.
- Successful results receive a saved-result URL, so inspecting them again uses GET and does not rerun the agents.

Synthetic inputs are stored as `SIMULATED`. Real **Check Nearby** observations remain `BROWSER` and use the same evaluation service. Evidence and Open Loop data already exist; the context test calls Context and Critic, without repeating screenshot perception or fabricating intentions. Existing bounded verification/revision behavior remains intact.

Only an actual approved SURFACE that passes the existing receipt, evidence, active-loop and delivery checks becomes a persisted notification. STAY_SILENT does not create one. No hardcoded decision or invented notification is inserted in this mode.

## Saved-location presets

**Load saved locations** reads existing entities and active loop views only on request. Eligible presets need:

- Stored valid latitude/longitude, `location_verified="true"`, and a nonempty coordinate source.
- An OPEN/ACTIVE linked intention with supporting screenshot Evidence.
- For shopping, the same verified physical-store association required by backend retrieval (`location_role="store"` and `store_name`). This never proves inventory.

The near preset uses a great-circle offset of 100 m; the far preset uses 4 km from the selected verified point. It does not promise that other saved places are absent at the far point. Accuracy defaults to 20 m. Fields remain editable and final retrieval/decisions remain backend-owned. Missing provenance, coordinates or active evidence links are explained rather than replaced with suburb-center coordinates.

The old `/entities` projection timed out after 60 seconds because it computes per-entity counts and related loop information. A new **read-only GET `/context-simulator/places`** returns entity ID/name/domain and only the six relevant coordinate/store metadata fields using one repository list read. Repository interfaces and SQL are unchanged.

**Deployment blocker:** Daffa's current backend returns 404 for this new GET route. He must run the reviewed code containing the additive route before saved-location presets work remotely. No remote files, process or deployment configuration were changed. Manual location/calendar/time evaluation and visual previews already work independently of that addition. The frontend explains a 404 and leaves manual inputs available.

## Real execution evidence — 27 October 2026

The private backend returned HTTP 200 for health, OpenAPI, notifications and both evaluations, with normal TLS verification through the Mac curl trust store. Health reported `mode=real`, workspace `canonical`, `ZetarisRepository`. Python's separate CA bundle could not validate the issuer; TLS verification was not disabled.

### Calendar: actual SURFACE

Submitted a clearly labelled synthetic **Lunch with Sarah** event in **Melbourne CBD**, next week at **12:30–14:00 Australia/Melbourne**, described as considering saved restaurant ideas. No positive decision was supplied.

| Record | Actual value |
| --- | --- |
| Evaluation | `eval_efb363449201976455d6b0921b3a09e8` |
| Run | `run_14a3e384920e` |
| Context | `ctx_pingo_calendar_ui_f0b16eb06133` |
| Context Agent | MATCH |
| Critic Agent | SURFACE |
| Intention | `loop_32d2b2760a9f` — Yamamoto Udon Izakaya, QV Square |
| Supporting Evidence | `ev_0aacd8a900928366f08c4512` |
| Persisted notification | `notice_run_14a3e384920e` |
| Initial delivery state | `APPROVED_PENDING_DELIVERY` / APPROVED |

Both actual model receipts report provider **nvidia**, requested and routed model **nvidia/nemotron-3-ultra-550b-a55b**. The concise reasons are in `artifacts/ui/notification-scenarios/real-calendar-result.json`; no hidden reasoning or credentials are stored in the report.

The notification was returned by the API. Browser verification opened its real Why now? page, received its original screenshot image with HTTP 200, and followed **View saved intention** to `/entity/loop_32d2b2760a9f`, where Yamamoto and **Your saved screenshots** rendered correctly. Delivery/read actions returned 200.

The notice was already READ by the time the banner capture ran. Its read status was preserved. `real-surface-banner-replay-390.png` is therefore an explicitly labelled replay of an actual persisted SURFACE notice, not a newly delivered unread banner. `real-surface-390.png` and `real-why-now-390.png` show actual saved results without API interception. Fresh unread display is separately covered by the offline browser contract test; it is not misreported as a live unread capture.

Open the stored real result without another model call:

`/context-simulator?mode=agents&evaluation=eval_efb363449201976455d6b0921b3a09e8`

### Distant location: actual STAY_SILENT

Submitted a SIMULATED location at latitude 0, longitude 0, accuracy 20 m.

| Record | Actual value |
| --- | --- |
| Evaluation | `eval_1e7277609562946dd7e1ed02105c4bb3` |
| Run | `run_9d84c56aac7d` |
| Context Agent | Native NO_MATCH |
| Final action | STAY_SILENT |
| Notification | None |

No candidates qualified, so the existing workflow did not make a Context model call or invoke Critic unnecessarily. This is a real safe no-match result, not proof of successful precise nearby matching: all geographic diagnostic entries in this run were unlocated. OMB Burger's actual metadata contains halal/late-night/price details but no verified coordinates. No coordinates were invented.

`real-stay-silent-390.png` shows the saved developer result and exclusions with no consumer banner. Open it at:

`/context-simulator?mode=agents&evaluation=eval_1e7277609562946dd7e1ed02105c4bb3`

### Actual deduplication and cooldown

Reposting the identical calendar body returned `replayed=true`, the same evaluation ID and run ID. It did not create a second notice. The distant evaluation's diagnostics marked the Yamamoto loop excluded by **cooldown** after its approved calendar ping. Notification count grew from 1 to 2 for the new SURFACE, and stayed at 2 after STAY_SILENT and replay.

Default server cooldown remains 6 hours; snooze remains 24 hours. Identical event fingerprints replay stored results; repeated new observations still respect loop cooldown and feedback. These policies and the existing SQL-backed persistence/retrieval failure cases also pass offline tests. No user feedback, read status, cooldown or loop status was reset to force a screenshot.

## Notification component and behavior

`NotificationBanner.tsx` is shared by local examples and the real polling center. It renders the supplied **`/brand/production/pingo-icon-192.png`**, app name Pingo, actual relative time (now for examples), short title, two-line body, source indicator and an independent 44px dismissal target. The transparent approved master remains `/brand/production/pingo-symbol-transparent.png`; no logo was redrawn.

Real banners use approved stored delivery text. The backend's generic boilerplate is presented as “Something you saved might fit this moment. Take another look?”; the actual full Critic reason stays in Why now?. No client copy invents distance, store inventory, calendar participants or availability. Example copy is confined to the explicitly labelled preview component.

Real dismiss calls the existing DISMISS action and removes the banner only after confirmation. Failed dismissal stays visible with a retryable error; duplicate clicks are guarded. Delivery acknowledgement requests are also guarded against duplicate concurrent submissions. Existing Done/Snooze/Not relevant/Just inspiration actions remain in the real detail view. Example taps open local explanatory content instead of fake entity IDs or backend actions.

Polling reads already-persisted notifications, pauses when the document is hidden, and never calls evaluation. Stable IDs preserve cards across refreshes. Read or dismissed notices are not deliberately replayed as new consumer notifications.

Authentication/session behavior is unchanged: this is the existing shared canonical workspace behind private tailnet access, without a separate frontend login/session in the inspected application code.

## Three delivery surfaces

1. **In-app banner:** implemented and visually tested in the open app.
2. **iPhone-style example:** custom web CSS, labelled as a simulation. It is not an iOS notification and does not request OS permission.
3. **Browser/system notification:** existing permission flow, service worker registration, `showNotification`, click handler and local deduplication remain present. Permission denial does not block in-app browsing or previews. Actual iPhone OS delivery is **not verified**.

There is no `push` event handler, PushManager subscription flow or backend Web Push sender in this implementation. Background Web Push therefore remains unimplemented. WebKit documents iPhone support for Home Screen web apps with a permission request triggered by direct user interaction: https://webkit.org/blog/13878/ . Native notification appearance is controlled by the OS.

Tomorrow's immediate GPS test must keep Pingo foregrounded over HTTPS/Tailscale and use **Check Nearby**. No closed/suspended-app background GPS behavior is claimed. Before a real nearby restaurant/store test, add genuinely verified place coordinates/source and any required store association through the existing data workflow; validate the active evidence graph. Deploy the new read-only preset route if you want convenience buttons. Calendar testing already works without that route.

## Screenshots and tests

Screenshots in `artifacts/ui/notification-scenarios/`:

- `restaurant-iphone-375/390/430.png`, `calendar-iphone-375/390/430.png`, `shopping-iphone-375/390/430.png` — local example content only.
- `shopping-in-app-390.png` — custom in-app example surface.
- `real-surface-390.png`, `real-surface-banner-replay-390.png`, `real-why-now-390.png`, `real-saved-item-390.png`, `real-stay-silent-390.png` — actual persisted backend data; replay qualification above.
- `contract-surface-fixture-390.png`, `contract-stay-silent-fixture-390.png` — explicitly mocked browser contract cases, not live AI proof.

Results:

- Backend offline suite: **280 run, 274 passed, 6 skipped**. This includes the additive projection test and existing notification persistence, failures, SURFACE, STAY_SILENT, shopping, cooldown and no-model polling tests.
- Frontend unit suite: **7 passed**, covering sorting/provenance, verified preset eligibility, store association, geographic offsets, honest delivery copy and denied OS permission.
- GPS browser suite: **7 scenarios passed** with mock GPS/API, not physical GPS.
- Preview browser suite: **9 mobile scenario/width combinations passed**, plus synthetic location/calendar submissions, correct saved-intention/evidence links, SURFACE display, STAY_SILENT suppression and polling separation. Added dismissal failure/retry and double-click checks use offline fixtures.
- `npm run build` / TypeScript check and `git diff --check`: passed.
- Actual calendar SURFACE, distant safe silence, persisted retrieval, receipts, replay and cooldown verified as described above.

Ordinary offline tests require neither Zetaris nor Nightshift. Browser harnesses require the local Vite app and a dedicated Chrome debugging session; their fixture mode intercepts all backend requests. Initial test-harness image-loading/canceled-request races were corrected with explicit waits/cleanup.

## Files changed for this task

- New: `frontend/src/features/notifications/NotificationBanner.tsx`, `NotificationVisualPreview.tsx`.
- Updated: `NotificationCenter.tsx`, `NotificationPreview.tsx`, `systemNotifications.ts`, `notifications.css` in the same directory; scoped `notification-tokens.css` makes this feature independent of the global design branch.
- Updated: `frontend/src/components/layout/AppShell.tsx` to separate visual-only mode from real notification polling.
- Updated: `frontend/src/pages/context/ContextSimulator.tsx`, `context.css`; new `contextPresets.ts`.
- Updated: `frontend/src/services/api.ts` for typed read-only preset and saved-evaluation reads.
- Updated: `backend/app/context/routes.py` with the additive read projection only; new `backend/tests/test_context_places.py`.
- New: `frontend/tests/contextPresets.test.mjs`, `notificationPreview.browser.mjs`; updated `liveLocation.browser.mjs` for the explicit agent-mode URL and test cleanup.
- This report and `artifacts/ui/notification-scenarios/` evidence/screenshots.

No agent implementation, orchestration, model routing, Zetaris adapter/repository, Evidence record, Home design, or environment configuration was modified by this task.
