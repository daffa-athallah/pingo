# Home presentation and catalogue media

The Home collection reads the existing `GET /open-loops` projection. Original Evidence, image files, repository methods and reasoning are unchanged.

## Minimal optional presentation extension

The current API does not supply verified catalogue photographs. The frontend therefore shows neutral category placeholders in real mode. Existing stock fixture photos and original Evidence screenshots are never promoted to catalogue images.

The frontend accepts this optional additive field on each existing OpenLoopView (no server persistence change was made):

```json
{
  "catalogue_images": [{
    "entity_id": "<one of this loop's existing entity IDs>",
    "catalogue_image_url": "https://<approved-media-host>/<image>",
    "catalogue_image_source": "<verified origin page or asset provenance>",
    "catalogue_image_verified": true,
    "alt": "<accurate description of this entity and variant>",
    "object_position": "50% 50%"
  }]
}
```

Verification must be established upstream by a trusted media curation process: exact entity/place, product variant, origin, rights, public browser-safe URL, and appropriate content. A `true` flag is a trusted backend assertion, not proof established independently by the browser. Never expose private local paths, credentials, or sensitive screenshot content. HTTPS images or app-owned `/media/`, `/images/`, `/catalogue/` URLs are accepted; the provenance source must be a public HTTPS URL without embedded credentials. A missing source, false verification, wrong entity ID, unsafe URL, multiple entities without a defined representative, or image-load failure produces a placeholder. No fuzzy name or filename matching exists.

`catalogueImage` is a frontend presentation field. It is separate from `screenshots`, which retain original Evidence IDs, timestamps, summary and backend image links. Detail exposes “Your saved screenshots” and links each thumbnail to the original-resolution backend view. Verified catalogue source credit is shown separately.

## Ordering and counts

Distinct screenshot count is the number of unique `evidence_id` values in the existing full `screenshots` array. Most recent uses the maximum valid linked screenshot `timestamp`; it does not read the loop's `updated_at`. Unknown timestamps sort last. Most screenshots sorts descending by distinct screenshot count, then latest screenshot time. Ties use stable loop IDs. `sort` and `category` are independent URL parameters, so switching categories and navigating back preserve sorting. The backend currently returns the full non-sensitive linked screenshot array. If that projection is ever paginated, it must also provide an authoritative distinct total and latest screenshot timestamp.

## Assets and UI

- Font: self-hosted Inter Variable from `@fontsource-variable/inter` 5.3.0, OFL-1.1.
- The current symbol is `/brand/pingo-symbol-reference.png`, the supplied RGB reference crop. It has no alpha channel. Per the user's instruction, it is preserved until an approved transparent SVG/PNG master is supplied. No new silhouette or transparency approximation has been generated.
- The notification opt-in card is removed from the application shell. Permission is requested only after opening `/settings/notifications` and choosing “Turn on notifications.” In-app polling/delivery remains mounted globally.
- The mockup's beautiful photos cannot be reproduced accurately for live entities until verified catalogue media is supplied. No mockup entity/title/photo has been inserted into real data.
