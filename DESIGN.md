# pingo frontend design system

The locked product name is lowercase `pingo`, without a trailing period. The product line is “Your screenshots have plans.”

## Visual direction

- White page canvas with warm cream (`#FFF6ED`) cards and restrained orange (`#FF763B`) accents.
- Primary text is charcoal (`#292522`); sand (`#E8DCCF`) is used for quiet borders and separators.
- The symbol is an asymmetric three-petal orange/peach mark with a detached dot. It must not become an arrow, play button, mascot, or generic blob.
- Typography is Inter Variable with normal, medium, and semibold weights and firm, low-curvature forms. Avoid bubbly or Picsart-like display lettering. The wordmark may use a small orange dot above the `i`.
- Depth is soft and tactile: faint shadows, translucent fixed navigation, and minimal satin-like highlight. Never use loud gradients or futuristic glass effects.

## Product hierarchy

Home foregrounds “Good things, saved.”: one curated catalogue of tentative interests discovered from screenshots. Its persistent header contains only the symbol and profile action. Compact category pills precede the hero; a small sort control sits above the collection. Category and entity views remain supporting layers. Check-in should feel conversational, and notification details must make “Why now?” and supporting evidence easy to understand. Agent Activity remains a technical proof surface and uses the same tokens without masquerading as a consumer dashboard.

## Interaction rules

- Mobile-first layouts must remain comfortable at 320px and become a centered reading column on desktop.
- Bottom navigation and the Home header remain visible while scrolling.
- Approved notifications appear as compact top banners; polling only fetches persisted decisions and never invokes agent reasoning.
- Orange actions use charcoal text when needed for contrast. All focus states are visible and reduced-motion preferences are respected.
- Home catalogue images require a verified exact-entity source; missing media uses a neutral category placeholder. Evidence screenshots remain accessible in Detail under “Your saved screenshots.” See `docs/frontend-catalogue.md`.
- Most recent follows the latest linked Evidence screenshot timestamp. Counts use distinct Evidence IDs. Sorting persists independently of category filters.
- Notification permission is requested from the user-opened notification settings route; no persistent permission card appears in the collection.

## Asset status

`PingoMark.tsx` renders the unmodified V2 production master at `/brand/production/pingo-symbol-transparent.png`. Home, Agents, and Check-in use this same transparent symbol at 36px, with the same 44px profile action. Supporting pages share `PingoPageHeader`; no wordmark or lockup is used in those persistent headers. The supplied cream-tile app icons, favicon and explicit maskable asset are wired into the web manifest and document head. No logo is redrawn or extracted by the application.

Agents and Check-in keep the same 480px reading column as Home, 28px semibold page headings, 14px body copy, cream surfaces, and charcoal selected pills. Agents preserves its four characters and event-driven states; the stage uses quieter cream/white surroundings and its run summary stays in document flow. Check-in keeps all response modes; options-only questions expose their choices directly, while confirmation questions retain yes/no and progressive clarification controls.

The V2 asset notes still flag automatic alpha-edge extraction for visual review and call the Inter wordmark a reproducible draft. Keep those qualifications visible in delivery notes; the monochrome SVGs are simplified contours, not replacements for the shaded PNG. The original supplied assets remain byte-for-byte intact in `frontend/public/brand/production/`.

Shared colors, surfaces, radii and motion load from the kit's `brand-tokens.css`. The app overrides the kit's suggested font stack with self-hosted Inter Variable, per the approved application brief. Page headings are 28–32px, section headings 20px, collection titles 16px, metadata 13px and body copy 14–16px.
