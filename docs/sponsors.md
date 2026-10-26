# Sponsor integration and evidence

Recall turns screenshot evidence and current context into a decision about whether to interrupt. The sponsors occupy specific boundaries: Zetaris is the canonical shared state, H-MEM expands retrieval, Nightshift executes model requests, and NVIDIA Nemotron supplies reasoning. Neither a database nor the memory engine is counted as an agent.

## Zetaris: grounded shared state

Canonical mode uses `ZetarisRepository` over JDBC, with native Iceberg tables in `recall_data.app`:

- `evidence`, `entities`, `evidence_entities`: immutable perception records and their entity graph.
- `open_loops`, `loop_entities`: tentative intentions and their supporting subjects.
- `context_events`, `context_evaluations`, `notifications`: explicit triggers, decisions and delivery state.
- `check_ins`: the person's clarification and merge feedback.

The agents read evidence and candidates through a common repository interface. The canonical implementation is Zetaris, not a local JSON store presented as SQL. Each returned model reference is checked against the records the agent was shown. Context-to-reminder output contains evidence IDs and context IDs so the result can be inspected.

The committed snapshot in `backend/demo/snapshot.json` has **30 Evidence, 65 entities, 69 Evidence↔entity links and 17 active loops**. These are exported historical counts, not a claim about future live totals; retired loops are excluded from the snapshot. Real mode's `/integration-status` reads current repository counts. The resettable demo and credential-free sample use explicitly labelled in-memory state and never claim to have written to Zetaris.

Repository `unit_of_work` scopes related writes and compensates failed operations. This is **not a distributed multi-table ACID transaction**. A failed or uncertain compensation blocks subsequent writes pending reconciliation; the MVP runs one writer. Tests in `backend/tests/test_zetaris_repository.py`, `test_ingestion.py` and `test_bootstrap.py` cover graph consistency and failed loop application. Local live round-trip evidence is described in [architecture proof](architecture/agent-orchestration.md#real-proof-verified-in-this-working-tree); the default offline test suite does not claim live JDBC verification.

## Meterless H-MEM: retrieval with provenance

The reference engine is vendored unmodified in `engines/hmem/src`, with its license and [upstream commit notice](../engines/hmem/NOTICE.md). Recall adds `server.ts` and the Python boundary `backend/app/hmem.py`.

After non-sensitive Evidence is stored, `HMemRepository` queries memory **before** remembering the new screenshot, avoiding self-matches. Historic memories are long-term; a new screenshot enters working memory. Each record carries a source, provenance references back to Evidence, confidence and an audit ledger. Returned IDs are resolved against the actual repository and sensitive/missing Evidence is withheld. Only valid hits expand the related-Evidence list already consumed by the unchanged Open Loop Agent. Memory never decides whether to interrupt.

The Elmo's recording demonstrates the gap it fills: the new extraction calls the venue “Elmo's Hamburger”, while earlier screenshots name “Elmo's Hamburger Restaurant”. They have different entity IDs. Entity-only retrieval finds **zero** prior records for that new entity. H-MEM adds **three** earlier Evidence records; the model then chooses ATTACH and supporting screenshots go **3 → 4**.

Verified scores from the bundled `attach` capture:

| Evidence | H-MEM relevance | Retrieval path |
| --- | --- | --- |
| `ev_b793a2e138d7d509d26670ff` | 0.4039 | H-MEM only |
| `ev_c8e07581a1c3fc2581ab2528` | 0.3731 | H-MEM only |
| `ev_cec51a5b7d33fc9401d77173` | 0.3684 | H-MEM only |

Threshold is 0.35, top 5. Scores vary with the actual extraction/query; these numbers describe this capture only. The reference embedder is a **hash mock**, and unrelated venues can receive marginal scores. The demonstrated capability is governed memory with provenance, confidence and auditability, not advanced semantic search. If memory is unavailable, the system reports it and continues with entity-linked retrieval. Sensitive Evidence is neither queried nor remembered.

Passing engine checks (run 26 October 2026):

```sh
cd engines/hmem
npm ci --ignore-scripts
HMEM_IMPL="$PWD/src/index.ts" ./node_modules/.bin/tsx conformance/runner.ts
# 13/13 checks passed
./node_modules/.bin/vitest run
# 10/10 reference tests passed
```

Recall's Python suite additionally starts the real sidecar in `backend/tests/test_hmem.py::RealEngine` when Node/tsx are installed. Its four tests verify Elmo's retrieval, provenance/confidence/ledger, mandatory source rejection and idempotent seeding. Stand-in transport tests are identified separately and are not used as proof that the real engine ran.

## Meterless Nightshift: every model request

All production calls follow:

```text
Recall agent → ModelGateway → Meterless Nightshift → configured provider/model
```

`backend/app/adapters/nightshift.py` discovers instance-advertised models before use, uses the Nightshift app/scope headers, strips leaked reasoning, and exposes sanitized routing receipts. There is no direct-provider fallback. Provider keys are configured inside Nightshift; Recall's environment contains only its Nightshift access configuration. An early direct-NVIDIA developer probe is archived in `backend/legacy/` and is not an application path.

Each agent payload carries a unique `request_id`. This mitigation was introduced after similar requests were observed returning another record's cached answer through the local Nightshift instance. It does not weaken schema or reference validation. Model timeouts, malformed output and invalid references use bounded retry and safe outcomes.

Trace receipts retain `requested_model`, `routed_model` and `provider`; no key, request header or chain of thought is exposed. Discovery alone is not proof of inference: the captured response receipts identify which route actually answered.

## NVIDIA Nemotron: decisions and critique

The bundled recordings identify `nvidia/nemotron-3-ultra-550b-a55b` with provider `nvidia` for Open Loop, Context and Critic, including duplicate review. Screenshot perception uses `gpt-4o-mini` with provider `openai`, also through Nightshift. We do not claim NVIDIA performed the vision step.

The revision recording shows a collaboration moment rather than a renamed linear chain:

```text
CONTEXT MATCH
  → CRITIC REQUEST_REVISION (booking/time unsupported by Evidence)
  → OPEN_LOOP REVISE (returns to a tentative venue interest)
  → CRITIC SURFACE (evidence + dinner context now support a suggestion)
```

Four separate recorded Nemotron replies pass the existing agent validators and orchestrator bounds. The unrelated dry-cleaning event takes the separate NO_MATCH → STAY_SILENT branch. A sensitive screenshot invokes only the vision route: no reasoning or memory call follows.

## What is distinctive, and what replay proves

A saved screenshot is treated as evidence for an **unfinished-intention hypothesis**, not an instruction or confirmed goal. H-MEM bridges a concrete retrieval gap, and the Critic has authority to withhold a reminder or demand that the interpretation be revised. Check-in gives a person the final say on ambiguous duplicates. Evidence stays traceable throughout.

`RecordedGateway` replays the **captured final model replies**, not precomputed final answers, through the existing parsers, validators and application boundaries. Exact request fingerprints include the model, prompt, evidence, image bytes, context and frozen test clock; only nonces are ignored. Recorded memory I/O goes through `HMemRepository`. Input drift fails closed with no live or scripted fallback. Cases use independent state; duplicate review uses a clearly labelled synthetic six-loop fixture.

Offline replay proves reproducibility of these cases and allows credential-free inspection. It does **not** prove fresh reasoning on arbitrary inputs, a new Nightshift call, a new H-MEM engine execution or a live Zetaris write. The separate real-engine tests and a live demo provide those other forms of evidence. See [capture/replay implementation notes](../backend/demo/recordings/README.md).

## Development and pre-existing work

Cursor was not used; no Cursor-development claim is made. [The current event rules](https://hackathon.genai.works/event/open-agent-hackathon-2026), section 5.1, make it optional, and section 6.4 asks for its use only if applicable. Older Academy/example material may differ.

Recall's first repository commit is dated 25 October 2026, inside the 22–27 October build window. Pre-existing components include the declared Apache-2.0 H-MEM reference implementation and the Python/npm dependencies listed in requirements/package files. The upstream engine is not claimed as team-authored work. Recall's adapter, model integration, orchestration, app and trace UI are the project work.
