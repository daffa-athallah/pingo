# Context Agent

**Question it answers:** *"Does something happening now make this intention relevant?"*

**Responsibility:** compare current context against the person's active Open Loops and say whether a connection exists. It does **not** decide whether to notify; `MATCH` only means "this loop may be relevant".

Code: [`backend/app/agents/context.py`](../../backend/app/agents/context.py).

## Input and output

| Input | Active loops (`OPEN`/`ACTIVE`, at most 30 most recently updated) with their entities; `ContextEvent`s |
| --- | --- |
| Supported context | `CALENDAR`, `LOCATION`, `TIME` |
| Unsupported | `REAL_WORLD_EVENT` exists in the model as a reserved type. No retrieval is implemented, and the agent rejects it as a trigger |

| Decision | Meaning |
| --- | --- |
| `MATCH` | A context event clearly connects to one loop (same place or area, same activity, fitting time). Requires loop, trigger type and cited context IDs |
| `NO_MATCH` | Nothing connects. A vague overlap is `NO_MATCH` |
| `NEEDS_VERIFICATION` | A connection is plausible but the context is unreliable or too thin. Requires uncertainty and a verification request |

Unknown loop or context IDs are rejected. Resolved, invalidated and dormant loops are never offered.

## Read-only

The Context Agent never creates or edits loops or Evidence. `assess_active` only reads active loops and their entities through the repository.

## Model routing

Agent → `ModelGateway` → Meterless Nightshift → NVIDIA Nemotron 3 Ultra. No direct fallback.

## Controlled context

Recall has no live calendar or location integration yet. For demonstration, [`backend/scripts/context_eval.py`](../../backend/scripts/context_eval.py) builds **synthetic** `ContextEvent`s (for example a calendar entry "Dinner with Alex") and runs them against a **real** Open Loop in Zetaris. The synthetic events are labelled as test input in the saved artifact; the Context and Critic decisions are real model output. In the recorded runs, "Dinner with Alex" in Fitzroy North matched the Elmo's Hamburger loop; "Pick up dry cleaning" in the same suburb did not result in a surfaced Recall (in two runs it was stopped once at the Critic and once at the Context Agent: model output varies between runs).
