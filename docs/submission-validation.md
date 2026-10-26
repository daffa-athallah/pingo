# Submission preparation validation

Validated on 26 October 2026. No commit, push, public-visibility change, HackOS submission or message to another person was made. Canonical backend/H-MEM services were not restarted or reset. Test screenshots were sent only to the isolated composition used for capture; no canonical screenshot upload occurred.

## Work completed by stage

| Stage | Change / files | Verification | Remaining limit |
| --- | --- | --- | --- |
| 1. Recorded judge mode | `backend/app/recorded.py`, `sample_cases.py`, `sample_api.py`, `sample.py`; seven JSON recordings and images; sample bootstrap/startup/context boundary; observer workspace labels; demo/Agent Activity/runs adapter; Docker packaging | 283 Python tests, 2 live-test skips; TypeScript + Vite; seven HTTP replays; Docker replay with network disabled and no Node | Fixed inputs and clock only; no fresh model inference in replay. Duplicate inputs are a labelled synthetic fixture. |
| 2. Judge setup | Root/backend READMEs, `backend/.env.example`, archived `backend/legacy/test_nvidia.py`, updated protocol-test/CLI imports | 283 Python tests, 2 live-test skips; diff whitespace check | Actual repository remains private; publish/commit decisions belong to Daffa. |
| 3. Sponsor explanation | `docs/sponsors.md`, links to implementation, receipts and tests | 283 Python tests, 2 live-test skips; H-MEM 13/13 conformance and 10/10 reference tests | Snapshot counts and captured model results are explicitly historical; no claims of a new database/model call during replay. |
| 4. Clean candidate setup | Fresh local clone of `main` at `7cefe20`, then uncommitted candidate patch/new files applied without committing | New venv + pip install; sample CLI/server; npm ci + frontend build; Docker build/start; all 7 cases via nginx proxy; 21 linked screenshot previews; no mutation of 17 browsing loops | This is a local clone plus proposed changes, not a public GitHub clone of an already-pushed submission. |
| 5. Team decisions | Repo status recorded as private; Daffa confirmed Reasoning Architecture; current official rules checked for optional Cursor usage | No code changes for decisions | Daffa must set the confirmed track in HackOS and approve public visibility. |
| 6. Recording plan | `docs/demo-script.md`: 3m30 video script, live/replay distinctions, eight-slide outline, human-owned actions | 283 Python tests, 2 live-test skips; TypeScript + Vite passed | The actual video, deck and HackOS submission are not created by this preparation. |

## Commands and results

```sh
backend/.venv/bin/python -m unittest discover -s backend/tests
# 283 tests, OK, skipped=2 (live Zetaris tests)
cd frontend
npx tsc --noEmit && npx vite build
# PASS
```

The candidate clone initially passed 283 tests with six skips before installing optional H-MEM Node dependencies. After `npm ci --ignore-scripts` in `engines/hmem`, it passed **283 tests with only the two live Zetaris skips**. The real engine's own conformance and unit tests also passed from that fresh installation.

```sh
cd engines/hmem
HMEM_IMPL="$PWD/src/index.ts" ./node_modules/.bin/tsx conformance/runner.ts
# 13/13
./node_modules/.bin/vitest run
# 10/10
```

Docker was tested under a separate Compose project (`recall-judge-check`) on ports 18120/15175. It required no env file. The final backend image replayed all seven cases under `docker run --network none -e SAMPLE_MODE=true ...`, reporting `Node: None`, `model_calls: false`. HTTP checks through the nginx frontend proxy verified health, runs, replay, synthetic case images, sensitive-image 404, arbitrary-input rejection and historical previews.

Known-key comparison against local credential values found **no matches** in the candidate source files. Env files, private runtime data, venvs, node_modules and excluded `HANDOFF.md` were not copied into the candidate. Docker context exclusions additionally cover env.local and handoff/config folders. This check is not a guarantee that arbitrary future additions contain no secrets.

No diff was made under `backend/app/agents/`, `backend/app/orchestration/recall.py` or `engines/hmem/src/`. No Ica-owned UI file was edited. Changes to the API contract are additive.

## Browser observations

Safari rendered the sample `/demo` case choices, the recorded revision trace, its Critic detail panel and Nemotron receipt, Home categories, empty product Check-in and the notification permission banner. The outdated integration-placeholder copy and sample storage labels were corrected. Actual notification delivery, mobile permissions and the final live recording still need Daffa/Ica's real-device check. No notification permission was granted during this validation.

## Expected recorded outputs

| Case | Output |
| --- | --- |
| attach | ATTACH, Elmo's supporting screenshots 3 → 4; three prior Evidence records supplied by H-MEM only |
| create | CREATE, new Kiwami hypothesis |
| sensitive | IGNORE; only vision called during capture; no reasoning/memory calls |
| surface | MATCH → SURFACE |
| restraint | NO_MATCH → STAY_SILENT |
| revision | MATCH → REQUEST_REVISION → REVISE → SURFACE; revision count 1 |
| duplicates | ASK/Check-in, MERGE and KEEP_SEPARATE on controlled synthetic inputs |

Tests emit Starlette/httpx deprecation and resource warnings, but no test failures. Live model capture did encounter schema/reference validation failures; the original validators rejected them, and successful captured cases use the existing bounded retry. Those validators were not relaxed.
