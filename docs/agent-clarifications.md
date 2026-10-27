# Agent uncertainty → Check-in → Open Loop

Implemented on `feature/notification-feedback-agent`, alongside the notification
feedback work. Main was fast-forwarded into this branch at `b827e00`. A private
local HTTPS preview runs this branch with a disposable in-memory workspace.
Nightshift discovery succeeded for both configured models; no live model-backed
clarification outcome is claimed by the offline tests below.

## When Pingo asks

- The existing screenshot upload workflow first runs Evidence and Open Loop as
  before. When Open Loop reports `material_uncertainty` (including
  LEAVE_UNRESOLVED), its new clarification method formulates one specific question
  with two to four choices using the same configured Nightshift reasoning model.
  The app adds “Something else” (requiring an actual explanation) and “Not sure
  yet.” Confident decisions do not trigger another call or a manufactured question.
- A real Critic ASK from the persisted context-simulator/live-browser evaluation
  workflow becomes a Check-in using the Critic's actual question, with free-text
  clarification or “Not sure yet.” It does not create a consumer notification.
- Missing/sensitive grounding and unverified model/provider receipts fail closed.
  Generation has one retry and a 30-second total deadline; an unavailable model
  does not create a pretend question or undo saved screenshot Evidence.

This is initiative at an explicit uncertainty boundary, not a periodic job that
invents doubts. The original Evidence/Open Loop/Context/Critic prompts and core
orchestrator branching are unchanged. New prompts are scoped to question
formulation and interpretation of an actual user answer. Integration is at the
existing upload/context application boundaries. Direct CLI calls to
`RecallOrchestrator.ingest_screenshot` do not independently queue Check-ins, and
the deliberately read-only legacy `/context/evaluate` route stays read-only.

## Existing data contracts

No new tables or repository methods. A `CheckIn` with kind
`AGENT_CLARIFICATION` uses the existing question JSON to store grounding,
uncertainty, origin and routing receipt. An empty `loop_id` explicitly means the
agent has not inferred an intention yet: no placeholder Open Loop is created.

The API adds optional `response_mode: "options"` and option
`comment_required: true`. Options-only questions do not show ambiguous generic
yes/no controls. Private question keys beginning `_` are stripped from public
GET responses. Original screenshots are served through the existing Evidence
image endpoint, never a local path. Sensitive/missing Evidence and closed targets
are not served. Agent clarifications remain available while unanswered; the
existing daily merge questions retain their original day rule.

`GET /api/check-ins` and `POST /api/check-ins/{id}/respond` keep their paths.
The answer response adds `agent_review`, with state/run ID/trace/decision.
Existing MERGE_LOOPS answers are unchanged. The Context evaluation response adds
`check_in_id` and `check_in_error`; simulator and foreground GPS refresh the
shared question state when a question was saved. Entering Check-in also refreshes
its data instead of relying on the initial app load.

## Answer lifecycle

1. Validate the selected option and any required explanation against that question.
2. Persist the actual answer before calling a model.
3. Open Loop receives the saved question, chosen label, user text, original
   Evidence/entities, and the current target intention when there is one.
4. Validate its existing LoopDecision schema and receipt; apply through the
   existing repository/persistence boundary. It cannot create a duplicate when
   a target exists or cite unsupported Evidence/entities.
5. Store the review separately. FAILED_SAFE/SKIPPED means the answer was saved
   but no inferred update could be confirmed; the frontend says so. KEEP/IGNORE/
   LEAVE_UNRESOLVED remains valid. No notification is generated from an answer.

An answer can create the first intention only when there was none and the actual
clarification supports it. If another upload formed a matching intention while
the question waited, it is offered as the target instead. A changed target or
new matching loop during reasoning rejects stale output. Screenshot Evidence is
never fabricated, rewritten or deleted by this path.

There is at most one retry under a 40-second total model deadline. Duplicate
identical answers return their saved review; conflicting later answers return
409. “Not sure yet” defers without a model call. Hard process interruption can
leave a saved RUNNING review: there is no automatic recovery worker or repeated
billing through GET requests. Existing Zetaris compensation scopes protect the
inferred mutation/review write; this does not invent JDBC transaction guarantees.

## Keeping questions lightweight

At most three outstanding agent clarification questions, one per entity set.
Pending questions suppress new contextual interruptions for the associated
intention/entities. Answered topics have a 24-hour question cooldown; repeated
image uploads or location checks do not ask the same question again. Original
screenshot ingestion still proceeds while a question is pending. These are
deterministic delivery safeguards, not hardcoded AI answers.

## Validation and rollout

Offline tests in `backend/tests/test_agent_clarifications.py` drive the actual
agent parser, upload HTTP route, SQL-harness repository, question API, answer
route, and Context/Critic workflow with explicitly labeled model fixtures.
They cover uncertain vs confident uploads, no fabricated loops, question budgets,
duplicate upload, day rollover, sensitive data, receipt rejection, retries,
answer validation, first-loop creation, target revision, newer-loop protection,
durable answers on model failure, deferral and read-only replay.

These tests do not prove live model behaviour or update Daffa's running server.
Deploy this reviewed branch to the backend and frontend together, preserving
the existing Nightshift credentials/model IDs and Zetaris configuration. No
schema migration is required where `check_ins` already exists. Previously
processed uploads are not silently reprocessed or billed again. Validate a new
real upload/run after deployment: a real uncertainty should emit OPEN_LOOP ASK
with a `checkin:` reference, followed by a pending question from the API. A
confident run may correctly create no question.
