# Recorded judge examples

These captures contain final structured replies returned by the configured Nightshift gateway, sanitized routing receipts, request fingerprints, and H-MEM query/store responses. No chain of thought, model credentials, request headers or image payloads are captured. The fixed inputs use the historical `backend/demo/snapshot.json`; test screenshots, context events and the deliberately over-specific revision title are synthetic.

`RecordedGateway` returns a captured reply only when the complete request fingerprint matches (including model, prompt, evidence, context and clock). Only request nonces are ignored. Agent parsers, ID validators, Open Loop persistence and the context orchestrator execute normally. Recorded H-MEM responses are replayed through the real `HMemRepository`; no Node process or live engine runs during replay. Each historical case starts from a fresh snapshot. Duplicate review uses the explicitly synthetic six-loop fixture in `duplicate_input.json`, adapted from the existing consolidation script. Original receipts attest to the capture, not a new provider call.

Cases: `attach`, `create`, `sensitive`, `surface`, `restraint`, `revision`, `duplicates`. The ingestion examples compose the existing Evidence Agent, ingestion bridge and Open Loop Agent using their public ID/clock injection points. Context and revision examples use the unchanged `RecallOrchestrator`; duplicate review uses the unchanged `Consolidator`. Replay results and Check-in questions belong to their isolated cases and do not change the browsing snapshot.

Run offline:

```sh
SAMPLE_MODE=true backend/.venv/bin/python backend/scripts/run_sample.py
SAMPLE_MODE=true backend/.venv/bin/python backend/scripts/serve.py --host 127.0.0.1 --port 8120
```

`GET /api/sample/cases` lists cases; `POST /api/sample/cases/attach/replay` reruns one. `GET /runs` exposes all replayed examples to Agent Activity. Arbitrary screenshot uploads and context evaluation are disabled in sample mode. Historical screenshot previews are served from the bundled `screenshot/` directory; the sensitive test image is never served.

To capture again (requires authorized Nightshift access, Node dependencies and a dedicated temporary H-MEM sidecar; never use the canonical engine):

```sh
# Terminal 1, from engines/hmem
HMEM_PORT=8317 HMEM_ALLOW_RESET=1 HMEM_PERSIST_DIR= ./node_modules/.bin/tsx server.ts
# Terminal 2, from repo root
backend/.venv/bin/python backend/scripts/capture_samples.py attach create sensitive surface restraint revision duplicates
```

Review captures before sharing. Outcomes are model output and are never forced; rerun the replay tests after any model, prompt, snapshot or fixture change. The endpoint fails closed if the inputs drift. All replay runs are `provenance: recorded`, `workspace: sample`, with synthetic inputs clearly labelled.
