# H-MEM in Recall

[H-MEM](https://github.com/Meterless/Meterless/tree/main/engines/hmem) is one of the four Meterless engines: a governed memory for AI agents.
Memories carry a mandatory `source`, `provenance` and `confidence`; they live in three tiers; retrieval blends semantic similarity, keywords, tags,
domain, entities, tier weight and recency, then multiplies by the memory's confidence (threshold 0.35, top 5); and every change is written to an
append-only trust ledger. This folder holds the unmodified reference implementation (see `NOTICE.md`) and `server.ts`, our small HTTP face over it.

## What Recall uses it for

The Open Loop Agent used to find related Evidence only through **shared entity IDs**. A new screenshot of "Elmo's Hamburger" has a different entity
from three saved screenshots of "Elmo's Hamburger Restaurant", so the agent saw no related Evidence and had to rely on loop titles. Now:

1. Every non-sensitive Evidence record is remembered in H-MEM: what the screenshot showed plus the names in it, `confidence` from the Evidence
   Agent's confidence, `provenance.refs = ["evidence:<id>"]`. The saved history is seeded as long-term memory; new screenshots start as working memory.
2. When a screenshot is saved, Recall first **asks H-MEM what it remembers** about it, then remembers it. H-MEM's hits are resolved against the real
   repository (ids that do not exist are dropped) and added to the related Evidence the Open Loop Agent already receives. The agent is unchanged.
3. The run trace shows `H-MEM:QUERY` (the hits, their scores, tiers and confidences, and why) and `H-MEM:STORE` (the new memory with its provenance),
   and the retrieval step marks each related Evidence as found via entities, H-MEM, or both. `GET /api/memory/ledger` serves the audit ledger.

Rules kept: sensitive Evidence is never remembered or queried; H-MEM unavailable never breaks a run (it falls back to entity links and the trace says
so); memory only adds retrieval candidates and never decides anything.

## Run it

The reference is TypeScript and uses syntax Node's built-in type stripping does not support, so it runs through `tsx`, exactly as the official README does.
Install once (the lockfile is the official one; install scripts are not needed):

```sh
cd engines/hmem && npm ci --ignore-scripts
```

```sh
HMEM_PORT=8300 HMEM_PERSIST_DIR=backend/runtime/hmem ./node_modules/.bin/tsx server.ts   # canonical (persistent), from engines/hmem
HMEM_PORT=8310 HMEM_ALLOW_RESET=1 ./node_modules/.bin/tsx server.ts                      # demo workspace (in-memory, resettable)
RECALL_HMEM_URL=http://127.0.0.1:8300 backend/.venv/bin/python backend/scripts/serve.py   # the backend then uses it
```

## Tests

```sh
cd engines/hmem
HMEM_IMPL=$PWD/src/index.ts ./node_modules/.bin/tsx conformance/runner.ts   # the official H-MEM conformance suite: 13/13 pass
./node_modules/.bin/vitest run                                              # the reference implementation's own unit tests: 10/10 pass
cd ../.. && backend/.venv/bin/python -m unittest backend.tests.test_hmem    # Recall's integration tests, including the real-engine ones
```

The stand-in engine inside `backend/tests/test_hmem.py` only exercises Recall's integration logic quickly; the `RealEngine` tests are the ones that
prove the actual H-MEM finds the earlier Elmo's screenshots that entity links miss. Set `RECALL_SKIP_REAL_HMEM=1` to skip them.
