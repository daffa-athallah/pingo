# Notification feedback → Open Loop Agent

Branch: `feature/notification-feedback-agent`.

The existing `POST /notifications/{id}/actions` now saves explicit feedback first,
then invokes `OpenLoopAgent.review_feedback` using the configured Nightshift
reasoning model. This is a new input path for the existing agent, not a new agent
or a rerun of screenshot perception. The original ingestion/Context/Critic prompts
and orchestrator branches are unchanged. Only the dedicated feedback prompt is new.

| User action | Immediate effect | Agent review allowed |
| --- | --- | --- |
| Done | Resolve the intention; stop reminders | Confirm RESOLVE; cannot reopen it |
| Snooze | Existing configurable snooze, default 24 hours | KEEP only; cannot infer abandonment/completion |
| Not relevant | Existing reminder suppression for this intention | KEEP or REVISE its title using existing Evidence; cannot infer completion |
| Just inspiration | Existing reminder suppression | KEEP, REVISE to an inspiration-only interpretation, or DORMANT |
| Dismiss / Read / Delivered | Existing notification state only | No model call |

For example, a person receiving a nearby brown-jacket reminder can select
“Just inspiration.” The agent sees that choice, the saved intention, its linked
entities and non-sensitive Evidence, and the originating reminder/context. It may
return DORMANT to pause the intention. An offline fixture tests that path; it is
not a claim that a live model has returned it. The agent may instead keep an
uncertain interpretation or revise its title. It cannot create a duplicate loop,
alter another loop, invent Evidence IDs, or modify screenshot Evidence.

## Persistence and safety

- No new tables, repository interfaces, endpoint paths, model IDs or routing rules.
- `notification.payload.feedback_review` stores state, action, run ID, timestamps,
  structured trace events, verified routing receipt and validated decision.
  Every feedback event also keeps its own `agent_review`, so a later snooze or
  final choice does not erase the previous review.
- States: RUNNING, COMPLETED, FAILED_SAFE, SKIPPED. KEEP is a successful review.
  Error/skip output never pretends the agent updated an intention.
- Explicit feedback is saved before the gateway is opened. Done and Snooze keep
  their effect even if configuration, model, parsing or review persistence fails.
- At most two attempts (one retry), under a 20-second total model deadline. The
  action response waits for this bounded review; the frontend shows a busy state
  and distinguishes a saved choice from a successful agent update.
- Application locks serialize feedback actions. Duplicate terminal choices and
  repeated snoozes inside the current snooze window return the existing result
  without another model call. Notification polling remains read-only.
- Failed or interrupted reviews are not automatically billed/retried by GETs or
  duplicate clicks. A hard process crash can leave RUNNING: explicit feedback
  survives, but there is no background recovery worker in this implementation.
- Missing/sensitive grounding, ineligible/closed intentions, and recorded sample
  mode without live models skip review. No sample outputs impersonate live calls.
- Applying a decision requires verified configured NVIDIA/Nemotron receipts. The
  model cannot override user completion, reinterpret a snooze as completion, or
  cite other Evidence. The loop is re-read before applying to reject stale output.
- The existing Zetaris compensation scope covers the inferred loop update and
  completed review record; it is not a JDBC transaction. SQL-harness tests cover
  compensation on a failed review save. Existing single-writer requirements and
  reconciliation limitations still apply. No transaction spans a model call.
- The action route invalidates the existing loop read cache. It does not create
  another notification or call Context/Critic to interrupt the user immediately.

The action response includes the audit metadata. Feedback traces are stored with
the notification, not registered as a new Agent Activity RunStore run. No hidden
chain-of-thought, credentials or raw model error responses are stored.

## Testing

```sh
backend/.venv/bin/python -m unittest backend.tests.test_notification_feedback -v
cd frontend
npm run build
```

Nineteen focused offline tests cover real parser/agent-method execution with
explicit fixtures, all feedback actions, persistence-before-call, deduplication,
receipt enforcement, malformed/unsafe decisions, bounded timeout/retry, sensitive
and missing Evidence, stale results, sample mode, HTTP response, SQL persistence,
and compensation. Live Nightshift/Zetaris execution and deployment are separate;
they have not been performed for this change. No Docker service is needed or
started for these tests.

Executed locally: all **19** focused tests passed; the combined feedback/context/
existing Open Loop checks also passed. Frontend build/typecheck passed. Full
offline discovery ran **346** tests: **339 passed, 6 skipped, 1 import error** in
the existing cover tests because Pillow is absent from the local environment
(already declared in `backend/requirements-server.txt`). No dependencies were
installed. `git diff --check` passed.
