# Critic Agent

**Question it answers:** *"Is this actually worth bothering the user about?"*

**Responsibility:** the final gate. A Context `MATCH` never surfaces on its own. The Critic reviews the loop, its supporting Evidence and the cited context, and returns a structured decision. It never notifies and never mutates loops, Evidence or context.

Code: [`backend/app/agents/critic.py`](../../backend/app/agents/critic.py).

> No Recall without evidence. No interruption without context.

## Decisions and routing

| Decision | Meaning | Next step |
| --- | --- | --- |
| `SURFACE` | Intention is well supported and the context makes it useful now. Must cite Evidence IDs and context IDs | Output layer |
| `STAY_SILENT` | Related but not useful enough, too weak, stale, redundant | Stop |
| `ASK` | One short clarification would materially improve the interpretation | Check-in |
| `REQUEST_REVISION` | The loop is over-specific, unsupported or inconsistent with the Evidence | Open Loop Agent (`REVISE`), then back to the Critic |
| `VERIFY_CONTEXT` | The trigger needs checking first | Context Agent via the verifier, then back to the Critic |

## Deterministic rules (no model call)

- Context `NO_MATCH` → `STAY_SILENT`.
- Context `NEEDS_VERIFICATION` → `VERIFY_CONTEXT`.
- Loop not `OPEN`/`ACTIVE` (`RESOLVED`, `INVALIDATED`, `DORMANT`) → `STAY_SILENT`.
- Any supporting Evidence marked sensitive → `STAY_SILENT` (MVP policy).
- No Evidence behind the loop → `STAY_SILENT`.

## Restraint

The prompt tells the Critic to compare the loop title with the Evidence first. If the title states a plan, date, timing, amount or action the Evidence does not show, it must choose `REQUEST_REVISION` even if the context fits. One screenshot is not treated as weak by itself. Location overlap alone is not a reason to interrupt.

## Output and explainability

A decision carries a concise reason (at most 400 characters), cited Evidence IDs, cited context IDs and, where relevant, a question, revision request or verification request. No chain-of-thought is requested, stored or returned.

## Model routing

Agent → `ModelGateway` → Meterless Nightshift → NVIDIA Nemotron 3 Ultra. No direct fallback.
