# Check-in

The `/check-in` route presents one question at a time, with positive/negative answers, optional clarification, progress, retry, empty, and completion states. It uses pingo's shared visual system. The backend lives in `backend/` (see the root README).

## Data modes

`checkInService.ts` selects the mode at build time:

| Environment | Mode |
| --- | --- |
| `VITE_CHECKIN_DEMO=true` | Explicit browser demo |
| Anything else | API (`GET /api/check-ins`, `POST /api/check-ins/:id/respond`) |

Questions are daily: each belongs to one calendar day, and `GET /api/check-ins` returns only today's unanswered ones. An unanswered question does not carry over; the backend's `daily_check_ins.py` creates the next day's. Today the backend produces "are these the same thing?" questions when the Critic is unsure whether two Open Loops are duplicates (supporting images are the two loops' screenshots). Answering "Yes, same thing" merges them; "No, keep both" and "Related, keep both" leave both loops alone.

The API base comes from `src/services/api.ts`: `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`. Configure it for a deployed backend before using production API mode. Configured backend failures remain visible errors; they never fall back to sample questions. Requests time out after 15 seconds.

Demo questions live in `sampleQuestions.ts`. Successful demo answers are stored in localStorage under `recall.checkin.demo.responses.v1`; answered questions are excluded when loading the demo again. Removing that key and reloading resets the demo. Demo mode is labeled in the interface, and its clothing previews are illustrative assets rather than user screenshots. Image provenance is recorded in [`public/images/checkin/sources.json`](../../../public/images/checkin/sources.json).

## API contract

`GET /api/check-ins` returns `{ "questions": CheckInQuestion[] }`. IDs must be unique. The service validates the response shape and reports malformed data as a load error.

```ts
interface CheckInOption {
  value: string
  label: string
  allows_comment?: boolean
}

interface CheckInQuestion {
  id: string
  loop_id: string
  type: 'CONFIRM' | 'CLARIFY' | 'STILL_RELEVANT'
  domain: 'shopping' | 'food' | 'destination'
  summary: string
  question: string
  supporting_images: { url: string; alt: string }[]
  options: CheckInOption[]
  positive?: CheckInOption
  negative?: CheckInOption
  context?: string
}
```

All question types show the two main answer controls and can expose clarification options through “Tell me more.” `positive` and `negative` override the controls' values and accessible labels. Without overrides, values default to `yes` and `no`; labels default to “Yes, that’s right” / “Not quite”, or “Still interested” / “Not anymore” for `STILL_RELEVANT`. Clarification displays `context`, falling back to `question`.

Selecting a clarification option submits its `value`. An option with `allows_comment: true`, or the value `other`, also reveals an optional comment field limited to 500 characters. Comments are trimmed; empty or inapplicable comments are `null`. At most three supporting images appear, and failed images are removed from the preview.

`POST /api/check-ins/:id/respond` uses an encoded question ID, `Content-Type: application/json`, and this body:

```json
{ "response": "yes", "comment": null }
```

Any successful HTTP response acknowledges the save; the frontend does not read a response body. The question advances and pending count decreases only after success. Save errors retain the current question and offer retry. Duplicate submissions are blocked while a save is in flight.

Skip advances without saving an answer or making a POST. Skipped questions remain unanswered, remain included in the navigation pending badge, and appear again when Check-in is revisited. Skipping the last question returns Home. The badge is hidden during loading, on load failure, and when no questions remain pending.

## Files and visual ownership

| File | Responsibility |
| --- | --- |
| `CheckInPage.tsx` | Route states, question sequence, skip, completion |
| `QuestionCard.tsx` | Question, image previews, responses and clarification |
| `CheckInProvider.tsx` | Shared loading, responses, submission and pending count |
| `checkInService.ts` | API/demo selection, request validation and demo persistence |
| `checkInTypes.ts` | Shared Check-in contract |
| `sampleQuestions.ts` | Demo fixtures |
| `CheckInIcon.tsx` | Local inline SVG icons |

`App.tsx` mounts the provider so `BottomNav.tsx` can show pending questions across routes. `AppShell.tsx` adds `checkin-shell` only on `/check-in`. Check-in styles and media queries belong to Ica's section 9 in the single `src/styles/global.css`, using `checkin-` prefixes and scoped shell overrides.

The visual brief follows pingo's white canvas, warm cream surfaces, orange accent, charcoal typography, narrow mobile shell, circular response controls, and overlapping screenshot previews. Shared tokens in `global.css` remain the source of truth; no separate design system or page stylesheet is introduced.
