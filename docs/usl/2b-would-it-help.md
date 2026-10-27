# 2b · Would a USL help our work, or not?

We build agent systems: software that remembers things, retrieves evidence, and has to explain its decisions. This is our assessment after
building one, split into where it earns its place and where it does not.

## Where it helps

**1. Explaining an agent's decision across systems.** An agent decision is never in one place. Ours touch a lakehouse (what was saved), a map
directory (where it is) and a decision log (who decided, on which model). Auditing "why did Pingo speak at 2:14 pm?" is a three-system join. With the
USL it is one query, and the vocabulary (`saved_place`, `reminder`, `agent_decision`) is the same one the product uses. For anyone building agents
that must justify themselves, that alone is worth the setup.

**2. Data quality over relationships, not just columns.** Column checks are easy anywhere. The rule that found our real defect (an open intention that
reaches zero screenshots) is a *relationship* rule across tables. Declaring keys in the USL and attaching rules to the logical tables is the first
approach we have used that made that check a one-liner.

**3. A shared definition.** "Verified place" meant different things in different parts of Pingo (an entity flag, a coordinate, a map match). In the USL it
is one column of one table, defined once. When teammates build on the same data, this stops arguments about whose number is right.

**4. Onboarding new sources without touching consumers.** We added the map directory and the decision log as new sources and the existing queries
did not change. In hand-written glue, each new source touches every script.

## Where it does not help

**1. The hot path.** Pingo's agents write evidence and intentions under a single-writer lock and need millisecond reads. Putting a federated layer on
that path would add latency and a moving part for no gain. The USL is an analytic and audit layer here, not the agents' storage, and we kept it that way.

**2. One-off questions.** For a single question the 42-line script was quicker to write and ran in about half the time ([2a](2a-time-saved.md)). If a
question will only be asked once, the USL is overhead.

**3. Tiny data.** Our lakehouse holds 42 screenshots. At that size a join in application code is trivial. The USL's advantages (federation, governance,
reuse) scale with the number of sources and consumers, not with rows. For one developer and one source it is the wrong tool.

**4. Fast-moving schemas without documentation.** The learning curve was steep. The DDL, activation, and data-quality statements are not documented in
the platform download, and several rules (multi-statement DDL separators, the local file root, `COMPILE` versus `DEPLOY`) were found by trial and
error ([2c](2c-product-requirement.md)). For a team without time to explore, that cost is real.

## Verdict

For *our* work, **yes, as a read-side layer for audit, explainability and data quality; no, as application storage.** The test we would give any team:
if three or more people will ask questions that cross two or more systems, build the USL; if one person asks one question, write the script.

## Bonus · a project that would benefit, with a forecast

**Project: a campus assistant for a university, "Where should I be, and what should I know?"** It would combine a timetable system (relational), a
buildings and rooms directory (CSV from facilities), live shuttle and event feeds (JSON) and each student's saved items (the Pingo lakehouse). Questions
that cross all four: *which of my saved cafés is within a ten-minute walk of my next class, open now, with a free seat?* A dozen such questions would
each be a different team's glue code today.

*Forecast (an estimate, not a measurement; the assumptions are the point):*

| Assumption | Value |
|---|---|
| Sources to combine | 4 |
| Cross-source questions the product and analytics teams need in the first quarter | 12 |
| Hand-coded cost per cross-source question (access code, joins, casts, review) | 30 min each, growing as sources are added |
| Cost per question through a built USL | about 3 min each |
| One-off cost to design, build and test the USL | about 1.5 working days (we took about 45 minutes for 3 sources once the syntax was known, and we expect a university's governance and access control to dominate) |

Hand-coded: 12 × 30 min ≈ **6 hours**. USL: 1.5 working days (12 h) once + 12 × 3 min (0.6 h) ≈ **12.6 hours**. So at twelve questions the
hand-coded route is still *cheaper*. Each extra question saves about 27 minutes, so the break-even is near **27 questions** (720 min ÷ 27 min), and
earlier if hand-written cost grows with every added source, which it does. We would not build this USL for twelve questions. We would build it for a
product that expects to keep asking, and the second-order effect is what we would be buying: the 40th question costs minutes, not an afternoon, and nobody
disagrees about what "free seat" means because it is defined once.
