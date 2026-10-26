# Open Loop Agent

**Question it answers:** *"What is this person still trying to do?"*

**Responsibility:** decide, for one piece of Evidence, how it changes the person's set of open loops. An **Open Loop is a hypothesis** about an unfinished intention, not a confirmed goal.

Code: [`backend/app/agents/open_loop.py`](../../backend/app/agents/open_loop.py).

## Decisions

| Decision | Meaning | Persistence (`apply`) |
| --- | --- | --- |
| `CREATE` | The Evidence supports a reasonable new intention. One screenshot can be enough | New loop, status `OPEN` |
| `ATTACH` | Evidence supports an existing candidate loop unchanged | Loop becomes `ACTIVE`, confidence updated |
| `REVISE` | Together with existing loops it shows a broader or different intention | New title/domain/confidence on the target loop |
| `RESOLVE` | Evidence shows an existing loop is done | Status `RESOLVED` |
| `IGNORE` | Nothing here is an unfinished intention | Nothing written |
| `LEAVE_UNRESOLVED` | Materially different interpretations cannot be told apart | Nothing written; `material_uncertainty` is required |

Loop↔Entity links (`subject`) are written for every cited entity except on `RESOLVE`.

## Grounding rules

- The agent receives the new Evidence and its entities, plus related Evidence, related entities and candidate loops that the repository returns.
- Every cited `evidence_id`, `entity_id` and `target_loop_id` must be one that was supplied; anything invented is rejected and the call fails safe.
- `CREATE`/`ATTACH`/`REVISE` must cite at least one Evidence ID.
- Titles must stay within the evidence: "Interested in this brown jacket" is fine; "Buy this jacket tomorrow" is not.
- Weakness is not screenshot count. It means inference exceeds the evidence, the evidence contradicts it, grounding is poor, or uncertainty is material.

## Revision

The Critic can send a typed `RevisionRequest` for one loop. In that mode the agent may only answer `REVISE` of the requested loop or `LEAVE_UNRESOLVED`; it cannot create a duplicate. The orchestrator allows at most one revision per run.

## Model routing

Recall agent → `ModelGateway` → Meterless Nightshift → NVIDIA Nemotron 3 Ultra. Receipts recorded for all real decisions in this repository show `requested_model = routed_model = nvidia/nemotron-3-ultra-550b-a55b`, `provider = nvidia`. Chain-of-thought is stripped by the gateway and never stored. There is no direct NVIDIA or OpenAI fallback.

## Real-data run

[`backend/scripts/process_open_loops.py`](../../backend/scripts/process_open_loops.py) runs the unchanged agent over Evidence stored in Zetaris, in stable order, one model call per eligible record, and writes loops back through `ZetarisRepository`. It is resumable (a ledger of processed Evidence IDs, and loop IDs derived from the Evidence ID, so a rerun creates no duplicates).

Local policy, applied before any model call: sensitive Evidence and domains outside `food`, `shopping`, `travel` are skipped. Original Evidence is never changed.

Result on the 30 imported screenshots: 22 reasoned over, 8 skipped locally (health 3, event 3, beauty 1, social 1) → 17 `CREATE`, 5 `ATTACH`, 0 `REVISE`/`RESOLVE`/`IGNORE`/`LEAVE_UNRESOLVED`, 17 Open Loops stored. Sanitized example:

```
loop_23a804535d76  "Interested in Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)"
domain food · status ACTIVE · confidence 0.85 · 4 supporting Evidence records (1 CREATE + 3 ATTACH)
uncertainty: could be browsing, saving for later, comparing options, or planning a visit; no action confirmed.
```

Known limits seen in the real output (not tuned away): three separate Air Jordan 3 sneaker screenshots stayed three loops rather than being merged, and an already-collected order (Spud Surprise Bag, 8 Oct 2026) was recorded as a loop instead of being resolved.
