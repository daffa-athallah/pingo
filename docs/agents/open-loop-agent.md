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

Result on the 30 imported screenshots: 22 reasoned over, 8 skipped locally (health 3, event 3, beauty 1, social 1). Final ledger: 17 `CREATE`, 4 `ATTACH`, 1 `IGNORE`, giving 17 active Open Loops. Sanitized example:

```
loop_62822173fdc0  "Interested in Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)"
domain food · status ACTIVE · confidence 0.85 · 3 supporting Evidence records (1 CREATE + 2 ATTACH)
uncertainty: could be browsing, saving for later, comparing options, or planning a visit; no action confirmed.
```

## What a real-data review changed

A first run recorded an already-collected order as a loop, and some decisions turned out to be stale replies from Nightshift's response cache. Causes and fixes:

- **No sense of today.** The input now has `now`, and the prompt says completed or past-dated things are not unfinished intentions (they are `IGNORE`d, or `RESOLVE` a matching loop).
- **Candidates were bare.** Candidate loops now carry entity names, brand and category, so the model can recognise the same item.
- **Merge only the same item.** Another screenshot of the exact product or venue is an `ATTACH`. A different variant (another colourway of a shoe) is a different item and gets its own loop; a later duplicate review, and ultimately the person via Check-in, decides about look-alikes. `REVISE` is for one clearly broader intention, not for joining look-alikes.
- **ID validation.** The validator rejected entity IDs from candidate loops even though they were in the input. It now accepts IDs the model was actually shown; invented IDs are still rejected.
- **Cache.** Each payload carries a unique `request_id` so every call is a fresh model call.

`process_open_loops.py --reprocess --only <evidence ids>` retires the loops those records created (status `INVALIDATED`, never deleted; the previous ledger is backed up) and reasons over them again with a new loop ID, so a retired loop's links are never inherited.
