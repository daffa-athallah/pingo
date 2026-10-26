# Impact: does Recall interrupt at the right moments?

**Problem.** People save places, products and trips as screenshots and then forget them when the moment arrives. A reminder system that interrupts too often gets switched off, so the hard part is **restraint with evidence**: speak when a saved intention clearly applies, stay silent otherwise, and never claim more than the screenshots show.

**Who it is for.** Anyone who saves food, shopping and travel ideas from social media and messages, and wants them back at the right time without noise.

## Measured: context decisions (real agents, real models)

`backend/scripts/benchmark_context.py` runs 20 synthetic calendar events against the 30-screenshot history through the unchanged Context Agent, Critic and orchestrator, with Recall → Nightshift → NVIDIA Nemotron answering. Gold labels come from construction: 10 events sit where a saved intention clearly applies, 10 are unrelated errands and appointments. Each event runs on a fresh in-memory copy; nothing is written to Zetaris. Full rows: [benchmark.json](benchmark.json).

| Measure | Result |
| --- | --- |
| Reminders on the 10 relevant events | **9 / 10** (recall 0.90) |
| Interruptions on the 10 unrelated events | **0 / 10** (precision 1.00) |
| Reminders that cite Evidence that exists | **9 / 9** |
| Runs that failed or errored | 0 |

The one miss ("Sam's birthday party" should have surfaced the saved ube cake) is the cheap kind of error: the system stayed silent. Raising recall without losing precision is the open problem, not a hidden one.

## Measured: what the history looks like

`backend/scripts/evaluate_impact.py` reads the committed snapshot (no model, no Zetaris): 30 screenshots became 17 active intentions, every one backed by at least one screenshot (0 without evidence), and 3 intentions are backed by two or more screenshots. Duplicate-looking saves are reviewed by the Critic and either merged, kept apart, or put to the person as a daily Check-in; the sample *Check-in* example shows all three outcomes.

## Honest limits

- The 20 events were written by the builders to be clearly relevant or clearly unrelated. This tests restraint and grounding, not how a real person's calendar behaves, and n = 20 is small.
- No user study has been run, so benefit to a person is not measured.
- Results depend on the model route; rerun the script to reproduce them (about a minute with Nightshift).

## How to strengthen it next

1. Have a few people label 30 of their own real events "would you want a reminder?" and compare against Recall's decision (precision/recall against human judgement).
2. Track how often a person answers a Check-in "same thing" versus "keep both", as a measure of whether the Critic asks only when it should.
3. Measure time-to-find: how long it takes to recover a saved place with and without Recall.
