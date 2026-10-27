# pingo — Production Brand Kit V2 integration

Publication split: the global design update is on `feature/pingo-design-v2`, based on notification commit `7a81875` from `feature/context-notifications`. Compare the design branch against the notification branch to review only branding, collection presentation and shared styling. Notification logic and its scoped banner styles remain in the base branch. Main has not been merged.

Implemented on `feature/context-notifications` without merging, committing, pushing, or modifying backend code. Existing uncommitted work was inspected and preserved. The V2 brief agrees with the existing Home structure, sorting and screenshot-provenance work, so those features were retained.

## Production assets

The supplied assets are copied unchanged into `frontend/public/brand/production/`. All 19 image/icon files match the archive byte-for-byte; SHA-256 records are in `artifacts/ui/brand-v2/asset-checksums.json`.

| Use | Exact supplied file |
| --- | --- |
| Home header, 36px | `pingo-symbol-transparent.png` |
| Check-in brand | `pingo-lockup-transparent.png` |
| Available wordmark | `pingo-wordmark-transparent.png` |
| Favicon | `favicon.ico`, `pingo-icon-32.png`, `pingo-icon-16.png` |
| Apple touch icon | `pingo-icon-180.png` |
| PWA and notification icon | `pingo-icon-192.png`, `pingo-icon-512.png` |
| Explicit maskable icon | `pingo-maskable-512.png` |

The shaded PNG master is used rather than the contour-traced SVG alternatives. No symbol or wordmark was redrawn. Header images use `object-fit: contain` without blend modes, opaque tiles, clipping, or altered aspect ratio. Browser canvas checks confirm the symbol's corner alpha is 0 and 47,884 fully transparent pixels. The supplied maskable icon is fully opaque (minimum alpha 255).

The manifest retains lowercase `pingo`, existing app ID/scope/start URL, white canvas, and the supplied cream theme color. Its icon paths are adapted to `/brand/production/` and include explicit `any`/`maskable` purposes. System notifications reference the same supplied icon family. Existing older assets were preserved but are no longer the active header/manifest references.

The kit's `PRODUCTION_ASSET_NOTES.md` still describes automatic symbol-background removal and requests review of the anti-aliased edges. It also calls the Inter wordmark a reproducible draft, not an approved bespoke font design. These are upstream asset qualifications; no alternate logo exploration was performed. The supplied header symbol was inspected on the app's white canvas.

## Typography and tokens

The supplied `design/tokens.css` is included as `frontend/src/styles/brand-tokens.css` and imported by the shared stylesheet. Palette, surfaces, radii and motion derive from those variables. The application deliberately overrides the kit's suggested Manrope-first font stack with the already self-hosted **Inter Variable**, per the implementation brief. No font dependency was added.

| Role | Applied size/weight |
| --- | --- |
| Mobile Home hero | 28px / 600, line height 1.2 |
| Desktop Home hero | 32px / 600 |
| Other page headings | 28–32px / 600 |
| Shared section headings | 20px / 600 |
| Collection titles | 16px / 600 |
| Collection metadata | 13px / 400 |
| Body text | 14–16px / 400 |

White backgrounds, cream cards, charcoal selected category pills and restrained orange accents remain consistent across Home, Category, Detail, Check-in and notification views. The Context Simulator retains its separate developer route and all location/calendar/time controls. Technical Agent Activity continues to use the shared token layer and its existing scoped component styles.

A visible focus frame around the entire main content was removed while retaining control-level keyboard focus indicators. Notification and Context Simulator headings now use semibold instead of the previous heavy weight.

## Data integrity and imagery

No entity names, evidence counts, timestamps, decisions or images were added to production data. Existing APIs and notification/context workflows remain unchanged.

- Home resolves only exact-entity catalogue metadata with a verified flag and a known HTTPS source. Missing/unverified media uses a neutral category placeholder.
- The current API has not supplied verified catalogue media. Beautiful factual restaurant/product/destination photos therefore remain a missing input, not a fabricated UI feature. See `docs/frontend-catalogue.md` for the existing optional contract.
- Detail retains the catalogue hero/placeholder followed by entity information and **Your saved screenshots**, linking to original Evidence images.
- Counts derive from distinct linked Evidence IDs. Recency derives from supporting screenshot timestamps. Category changes preserve the selected sort.
- No Evidence files, Zetaris records, backend contracts, model routing, agents or orchestration were changed.

## Browser validation

Rendered screenshots and metrics are in `artifacts/ui/brand-v2/`:

- `home-375.png`, `home-390.png`, `home-430.png`, `home-768.png`, `home-1440.png`.
- `category-390.png`, `detail-390.png`, `checkin-390.png`, `checkin-expanded-390.png`, `why-now-390.png`.
- `home-empty-390.png`, `home-error-390.png`, `checkin-empty-390.png`.
- `results.json` records viewport/scroll widths, computed fonts/colors, counts, routes, logo transparency, manifest assets and browser errors.

**Populated screenshots use intercepted UI fixtures, not live Zetaris or agent results.** The remote backend was unavailable during this task. The fixtures exist only in the browser test harness and never populate the application or database. The OMB detail fixture displays the unchanged local original screenshot; catalogue placeholders are used instead of unverified photos. Notification delivery/read POSTs in the harness are intercepted, not sent to the backend.

Verified: no horizontal overflow at the five target widths; no Vite overlays or browser exceptions; white canvas and exact cream cards; header symbol only; no permanent notification permission panel; sort preserved across categories; original evidence deduplicated; friendly error/empty states; sticky header top at 0 during a short-viewport scroll; valid manifest icon URLs and lowercase app name.

At 390px, cards are 350×128px with 112×112px thumbnails; at 375px, cards are 343×116px with 100×100px thumbnails. Cards remain within a narrow centered collection on desktop. Physical iPhone safe areas and installed-app icon refresh still require device review; responsive browser emulation does not prove those behaviors.

Validation passed:

```sh
cd frontend
npm run build  # includes TypeScript typecheck
```

The two existing collection sorting/provenance tests passed. `git diff --check` passed. Backend tests were not rerun for this frontend-only asset/token change.

## Files changed for this task

- `frontend/public/brand/production/*` — supplied files, unchanged.
- `frontend/src/styles/brand-tokens.css` — supplied token stylesheet, unchanged; application font override remains in global CSS.
- `frontend/src/styles/global.css` — token import/aliases, shared scale, transparency rendering, supplied lockup styling and main focus-frame fix.
- `frontend/src/components/brand/PingoMark.tsx`, `PingoBrand.tsx` — supplied transparent assets.
- `frontend/index.html`, `frontend/public/manifest.webmanifest` — production favicon/touch/PWA asset paths and theme metadata.
- `frontend/src/features/notifications/systemNotifications.ts` — production notification icon paths only.
- `frontend/src/features/notifications/notifications.css`, `frontend/src/pages/context/context.css` — semibold page headings.
- `DESIGN.md` — current asset status and shared token/type decisions.
- This report and `artifacts/ui/brand-v2/` verification files.

Remaining difference from the approved Home mockup: catalogue photography is absent until verified exact-entity media is supplied. The layout follows the mockup within the approved 28–32px hero and compact-card scale. The physical phone frame/status bar in the mockup is intentionally not reproduced as webpage content.
