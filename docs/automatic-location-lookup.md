# Automatic saved-place lookup

Implemented on `feature/live-gps-test`. Latest `origin/main` was fast-forwarded into this branch at `e676d70`, preserving local lookup changes. No Docker start, live database write or Daffa deployment change was performed.

## What changed

Main already contains Daffa's `geocode.py` and a post-upload location hook. This implementation reuses that module/API shape and extends it while preserving main's cover-image workflow. It does not replace the four agents or change their prompts, model routing, repository protocol, or orchestration branches.

The existing workflow is now:

1. Evidence Agent reads the screenshot via the existing Nightshift route.
2. The ingestion bridge saves canonical Evidence, Entities and their links.
3. The existing Open Loop step runs unchanged.
4. A bounded location tool automatically looks up the non-sensitive physical places/stores linked to that saved Evidence.
5. Only an unambiguous result updates entity metadata through `save_entity`.
6. Future Context/Critic evaluations use the same existing geographic retrieval and interruption rules.

The map tool is not another reasoning model. `LOCATION` events identify actual lookup outcomes without fake model receipts. There are no additional GPT/Nemotron calls for location lookup. Upload outcome `locations` reports resolved, located, ambiguous, not_found, unavailable, stale, skipped or store_failed states separately from the saved screenshot/agent result.

## Matching and provenance

- Search uses the extracted entity name, saved city/suburb/country and visible address when present. No filename/folder classification or hardcoded venue mapping is used.
- Primary name/locality query results are combined before accepting a match; the first result is not accepted blindly.
- Safe fallbacks include a name search inside a uniquely matched area boundary and an exact-name query whose results still must match the saved locality.
- Unicode/accent/apostrophe normalization handles ordinary spelling differences. Generic venue descriptors may be omitted, but extra distinctive name words are not treated as the same venue.
- A city occurring only inside the business name does not establish geography. Saved locality components must match whole returned address components, or an independently matched area boundary must contain the point.
- Multiple branch matches more than 50 m apart stay ambiguous. A provider result cap also prevents automatic selection. Nearby map duplicates do not create duplicate entity records.
- Invalid/infinite/out-of-range coordinates, missing OSM IDs, or malformed responses never become verified coordinates.
- Shopping **products and brands are not geocoded as shops**. Explicit store/shop/retailer entities may be resolved and receive a store role; nothing establishes item inventory.
- Broad city/suburb centroids are not invented as precise restaurant locations. Unresolved places stay unlocated, so existing Context retrieval remains silent about precise proximity.

Metadata stays in the existing entity JSON, without schema changes:

`latitude`, `longitude`, `location_verified`, `location_source`, `location_id`, optional `location_role`/`store_name`, and `location_lookup_status/at/signature/retry_at/reason/candidates`.

Candidates are bounded, auditable map replies, not AI guesses or automatically approved branches. The source explicitly credits OpenStreetMap contributors/Nominatim and identifies the OSM object. The developer simulator includes the attribution link. Original Evidence records and image files are unchanged.

## Repeated screenshots, privacy and failures

The ingestion bridge preserves independently obtained location metadata for the same stable entity ID. New perception attributes cannot forge `location_verified`, latitude/longitude or lookup provenance. If a new saved suburb conflicts, the old pin loses verified status pending a fresh lookup instead of silently being used for the new place. Stable entity identity rules remain unchanged.

Sensitive or ungrounded entities are never queried externally. A concurrent user-supplied verified pin is preserved, and results for entity details changed during lookup are rejected as stale. The latest entity metadata is read again before saving. A map timeout/outage or metadata-write failure does not undo or delete already-saved screenshot Evidence or change the agent decision.

There is no new distributed transaction guarantee: the existing application/repository still requires one writer for this MVP. The existing in-memory repository gained the same `save_entity` helper already present on main and in the Zetaris repository; the agent protocol was not changed.

## Public Nominatim configuration

The user explicitly selected public Nominatim for this small hackathon. Its [usage policy](https://operations.osmfoundation.org/policies/nominatim/) requires identifying requests, cache, maximum one request/second, and one host for small one-off batches. Do not deploy this as a generic public map-search service or schedule regular public-provider bulk jobs. A private/hosted compatible endpoint can be substituted through configuration.

In the ignored backend environment file on the backend host:

```dotenv
RECALL_GEOCODE=on
RECALL_GEOCODE_URL=https://nominatim.openstreetmap.org/search
RECALL_GEOCODE_USER_AGENT=Pingo-Recall-hackathon/1.0 (https://github.com/daffa-athallah/recall)
```

The example file defaults to **off**. Enabling requires an explicit operator setting, not detection of whether the program happens to be running under unittest. `SAMPLE_MODE=true` always disables it.

The transport serializes requests using a thread lock and a shared filesystem lock, with at least 1.1 seconds between outgoing requests. All processes on that host must share `RECALL_GEOCODE_CACHE_DIR` (default `backend/runtime/geocode`). Positive/negative provider responses are cached for 24 hours. Failures trigger a provider backoff; HTTP 429 respects a bounded Retry-After. Entity-level unresolved attempts also have retry times, so another screenshot does not keep searching the same place.

The cache is disposable provider response data, not an alternative application database. Canonical coordinates remain in Zetaris. TLS verification stays enabled. No new dependency, service, API key or Docker container is required.

## Existing screenshots: dry run first

The reused `backend/scripts/backfill_locations.py` processes existing active intentions using the same tool. Run on the actual backend host with its existing env-file paths; the example paths below match the existing deployment script and must exist there:

```sh
RECALL_GEOCODE=on backend/.venv/bin/python backend/scripts/backfill_locations.py \
  --env-file env.local --env-file backend/.env \
  --limit 10 --report backend/runtime/location-dry-run.json
```

This performs provider lookups and may populate the local cache, but does **not** update database records. Review candidates and statuses. Only after that review, add `--apply` to save entity metadata. `--entity-id ID` can select specific saved entities. Re-running skips verified/recently attempted entities; `--force` bypasses unresolved entity retry timestamps but never provider cache/rate limits. Each run is limited to at most 20 entities. No perception/model call is repeated.

No live apply was executed here: Docker remains stopped on this laptop, and Daffa's environment requires coordinated deployment. Integrate the changed location modules, upload hook, bridge and configuration into his reviewed checkout before testing new automatic enrichment on the deployed app. Existing main already has separate manual pin/candidate confirmation UI; it was not replaced.

## Executed validation

- Full offline backend suite: **316 run, 310 passed, 6 skipped**. New coverage includes matching/ambiguity, country/city/suburb checks, validated region fallback, malformed coordinates, caching, cross-client throttling, backoff, privacy, retries, stale writes, failed writes, SQL-harness persistence, dry-run behavior, metadata preservation and automatic upload integration.
- Upload tests prove the same vision/reasoning call count; map fixtures add no model calls and no fake receipts. Sensitive uploads send no map query. Another screenshot preserves a verified pin without another lookup.
- Frontend build/typecheck passed. The only frontend addition is a map attribution line in the existing developer simulator.
- After incorporating main at `e676d70`: **327 tests run, 320 passed, 6 skipped, 1 module import error** because the local environment lacks Pillow, now declared in `backend/requirements-server.txt`. No dependencies were installed. Frontend build/typecheck and diff checks still passed.
- `git diff --check` passed.
- Live read-only provider check for existing **Gimlet** returned OSM node **11466812433**, matching the saved source. An unrelated Gimlet-Lightwood Walkway was also returned by the provider; distinctive-name matching keeps it separate.
- Live read-only lookup for saved **Maison Batard** (`ent_bb4937f7fb29`) returned **not_found** for the address/name forms tested. It was not assigned fabricated coordinates. Repeating the same lookup caused **0 additional network requests** because the replies were cached.
- These live probes made **0 database writes and 0 model calls**. Results are local in `artifacts/live-location/automatic-lookup-probe.json` and `known-place-provider-check.json`.

This proves automatic tool integration and provider access, not complete map coverage. A missing venue or ambiguous chain still needs a better verified source or existing pin-confirmation workflow. This change does not itself alter the separate far-away location chip on Daffa's newer frontend.

## Changed files

- Added/reused: `backend/app/geocode.py`, `backend/scripts/backfill_locations.py`.
- Added: `backend/app/adapters/geocoding.py`, `backend/app/location_lookup.py`.
- Updated: `backend/app/upload_api.py`, `backend/app/ingestion/evidence_bridge.py`, `backend/app/repositories/memory.py`, `backend/.env.example`.
- Added: `backend/tests/test_location_lookup.py`, `backend/tests/test_upload_location_lookup.py`.
- Updated: `frontend/src/pages/context/ContextSimulator.tsx` (attribution only).
- This report and local probe artifacts.
