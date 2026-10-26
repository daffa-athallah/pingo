# Demo video and slide outline

This is a recording script and an eight-slide outline, not a completed video, slide deck or HackOS submission. Target length: **3 minutes 30 seconds**. Daffa confirmed the primary track: **Reasoning Architecture**. Use that track in the recording and HackOS submission.

## Before recording

1. Use a charger, keep the lid and Nightshift open, and run `backend/.venv/bin/python backend/scripts/preflight.py`. Coordinate canonical availability with Ica; do not restart it while she is testing.
2. Use the resettable demo workspace on **8100**, not canonical **8000**. Its storage is an in-memory copy of the historical Zetaris snapshot. Point the frontend at 8100. The `/demo` badge must say demo workspace / real models. A separate H-MEM instance runs on 8310; never reset canonical H-MEM on 8300.
3. Daffa chooses a **real food/shopping/travel screenshot never ingested before**, with no private messages, credentials or other sensitive content, and checks he is comfortable sending it through the configured Nightshift vision route. Synthetic test images in `backend/demo/recordings/images` do not count as that live input. No screenshot is supplied or uploaded by this script.
4. Frame the app so keys, terminals with `.env`, account tabs and private data are not visible. The browser tab title currently uses the existing Pingo UI branding; coordinate any branding change with Ica rather than editing her files silently.
5. Inspect Home, `/demo`, `/agent-activity`, Check-in and the notification display before recording. Sample-mode Home/demo/Agent Activity/empty Check-in and the permission banner have been inspected in Safari; actual push delivery and a live notification card still need a real-device check. Do not grant permissions merely to manufacture footage.
6. Keep terminal or API evidence for current Zetaris counts and H-MEM tests ready. Demo storage events must remain `REPOSITORY`; show the canonical read-only integration status separately if demonstrating Zetaris.

Suggested isolated live setup (from repo root unless noted):

```sh
# Terminal 1: from engines/hmem, after npm ci --ignore-scripts
HMEM_PORT=8310 HMEM_ALLOW_RESET=1 HMEM_PERSIST_DIR= ./node_modules/.bin/tsx server.ts
# Terminal 2: from repo root; Nightshift configuration is in ignored backend/.env
RECALL_HMEM_URL=http://127.0.0.1:8310 backend/.venv/bin/python backend/scripts/serve.py --demo
# Terminal 3
cd frontend
VITE_API_BASE_URL=http://localhost:8100 VITE_CHECKIN_DEMO=false npm run dev -- --host 127.0.0.1 --port 5175
```

Use only disposable demo state for rehearsals. Choose a different never-ingested real screenshot for the final live run; do not present a duplicate or replay as new model execution.

## Video: 0:00–0:20 — person, problem, outcome

**Show:** Home with saved food/shopping/travel interests, then a supporting screenshot.

**Say:** “We save screenshots of places, products and trips, then forget them when they would actually help. Recall turns those saves into tentative intentions and brings one back only when the current context makes it useful. Our entry is for Reasoning Architecture: evidence, memory and critique work together to decide when to interrupt—and when to stay silent.”

No measured impact claim is made. The intended benefit is less searching through screenshot folders at a decision moment.

## 0:20–0:45 — collaboration and authority

**Show:** Architecture diagram from the README, with the Critic → Open Loop return path visible.

**Say:** “Four agents have different authority. Evidence describes what is visible. Open Loop infers an unfinished interest, not a confirmed plan. Context asks whether anything happening now is relevant. The Critic can surface it, stay silent, ask a question or send an unsupported interpretation back for revision. The orchestrator enforces one retry and bounded revision; it does not make model decisions.”

## 0:45–1:40 — a genuine live screenshot run

**Show:** `/demo`, the demo workspace badge, then upload Daffa's never-ingested screenshot once. Let the actual Evidence, repository, H-MEM, retrieval and Open Loop steps arrive. Open the structured retrieval and before/after state in Agent Activity.

**Say while it runs:** “This is a new screenshot going through real models via Nightshift. We are using an isolated copy of our history for recording, so the demo does not append test records to canonical Zetaris. Here is what Evidence extracted. H-MEM queries the earlier history before remembering this screenshot, then the Open Loop Agent decides how it changes the saved interests.”

**Describe the actual output**, not an expected one. If it ATTACHes, show the existing loop and supporting screenshot count. If it CREATEs, show the new tentative interest. If it declines or fails validation, show the honest result; do not edit the trace or imply success.

Model latency varies. If the edit shortens waiting, visibly label the time cut and keep request/run IDs consistent. Never substitute a prerecorded synthetic case for this live segment without naming it as recorded.

## 1:40–2:15 — relevance versus restraint

**Show:** Two explicitly synthetic context inputs sent to the real-model demo workspace: “Dinner with Alex” in Fitzroy North, versus “Pick up dry cleaning”. For a live rehearsal, adapt dates to the current local date so the dinner has not already passed.

**Say:** “The calendar event is test input. The decisions are live. A relevant dinner can connect to a saved venue; the Critic still has to approve the interruption. An unrelated dry-cleaning event should end quietly. Silence is a useful outcome, not an error.”

Example API shape (use the real date for the final recording):

```json
{
  "synthetic": true,
  "events": [{
    "context_type": "CALENDAR",
    "title": "Dinner with Alex",
    "occurs_at": "2026-10-27T19:00:00+11:00",
    "location_name": "Fitzroy North",
    "city": "Melbourne",
    "country": "Australia"
  }]
}
```

Send via `POST http://localhost:8100/api/context/evaluate`; it is read-only and saves a run for Agent Activity. A live run is not guaranteed to take the desired branch. If you use the offline case buttons instead, switch to sample mode and say **“This is a recorded real-model decision being replayed, with synthetic context.”** Do not call it live. Show the Why-now reason, supporting Evidence and cited context when SURFACE actually occurs.

## 2:15–2:45 — the non-linear collaboration moment

**Show:** The captured revision case in sample Agent Activity, prominently labelled **Recorded real run, replayed**. Select `REQUEST_REVISION`, `REVISE`, then `SURFACE`; keep the receipt panel visible.

**Say:** “This controlled fixture deliberately claimed a booking time the screenshots never showed. In this recorded real-model run, the Critic rejected that interpretation. Open Loop revised it back to a tentative interest, and only then could the Critic approve a grounded suggestion. This is replayed for reproducibility; four actual Nemotron replies were captured through Nightshift.”

The recording proves the return path; it does not establish that the person intended to book. If recording a new live revision run instead, use the same throwaway fixture boundary and label the title/context synthetic. Never alter canonical loops for the video.

## 2:45–3:10 — sponsors with evidence

**Show:** Read-only canonical Zetaris integration counts; the Elmo's recorded H-MEM query/retrieval; model receipts; compact passing test output.

**Say:** “Zetaris is the canonical shared evidence and intention graph. H-MEM fills a retrieval gap: one Elmo's extraction shares no entity ID with three earlier screenshots, yet memory retrieves those three with provenance and confidence. Every model call goes through Nightshift. Nemotron handles intention, relevance and critique; GPT-4o-mini handles perception. These receipts identify which model answered. The H-MEM reference engine passes 13 conformance checks and 10 reference tests.”

Show sample storage as in-memory; do not imply the current replay performed a database write or invoked the engine. Do not claim federation over several enterprise sources, a production semantic embedder, or an unused sponsor tool.

## 3:10–3:30 — useful output and reproducibility

**Show:** Final grounded reminder with why-now/evidence, or the honest silent outcome; then the README quick start and seven-case list.

**Say:** “The result is a saved interest brought back with evidence at a useful moment, while unrelated or unsupported reminders stay quiet. Judges can run seven labelled recorded examples without keys, a GPU or local services. Live mode accepts new inputs through the same agents. Our next steps are verified real-device context, a real context verifier and better semantic embeddings.”

Finish under four minutes. If the live run takes longer, shorten narration or use a labelled time cut; do not remove the evidence needed to distinguish live execution from replay.

## Eight-slide outline

| Slide | Main message | Evidence / visual |
| --- | --- | --- |
| 1. A screenshot saved is an intention easily lost | People save food, products and trips, then cannot recall them at the right moment. Name the target user and primary track. | One real, shareable screenshot and the moment it could help. No invented user metric. |
| 2. Recall brings the right save back | Evidence → tentative intention → context → Critic-approved reminder or silence. | A reminder with its original Evidence and Why-now reason. |
| 3. Four agents, one accountable decision | Distinct roles, shared state, Critic authority and bounded return path. | README diagram; highlight REQUEST_REVISION → REVISE → Critic. |
| 4. Working implementation | FastAPI/Python, React/TypeScript, JDBC/Iceberg, H-MEM/TypeScript, Nightshift model gateway. | Repo modules and three-mode comparison. No Cursor-use claim. |
| 5. Sponsor technology does specific work | Zetaris grounds the graph; H-MEM expands retrieval; Nightshift routes calls; Nemotron reasons. | Elmo's zero entity-linked prior records → three memory hits; original receipts; 13/13 and 10/10. |
| 6. What is distinctive | Remembering a save does not authorize an interruption. A Critic can revise an inferred intention; the person settles ambiguous duplicates. | Revision trace plus ASK/Check-in from the labelled synthetic duplicate fixture. |
| 7. Product and reproducibility | Live screenshot ingestion, grounded result, restraint and inspectable activity; judges can inspect seven cases without credentials. | Actual rendered Home/demo/Agent Activity and a real output. Label every live/replayed/synthetic input. |
| 8. Limits and next steps | Hypotheses, word-list privacy, verified-location gap, no real context verifier, hash mock embedder; plan verified device context and better retrieval. | Public repo/video links only after they exist; state the tested run command and declared upstream components. |

## Final human-owned actions

- Select the confirmed primary track, Reasoning Architecture, in HackOS.
- Review data/licensing and explicitly make the repository public when ready; it is currently private. Commit/push require Daffa's permission and have not been performed by this work.
- Send Ica the agreed pull notice only after the changes are actually committed/pushed. No message has been sent on Daffa's behalf.
- Record the genuine live screenshot segment, create/export the actual slide deck, and submit the repo/video/deck and sponsor explanation in HackOS.
- Deadline: **28 October 2026, 10:45 AEDT (27 October, 23:45 UTC)**. Leave time to check that judges can open the links.
