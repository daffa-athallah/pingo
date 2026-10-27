# 2a · How the USL saved time versus a hand-coded approach

Short version: **the USL did not make our first query faster to write. It made every query after the first one nearly free, and it made one
class of mistake visible that hand-written glue never would have.** The numbers below are measured where we could measure and marked *estimate*
where we could not.

## The same question, both ways

Question: *which verified places does each open intention point at, with address and coordinates?* It crosses three kinds of data: Iceberg tables
(intentions, entities, links), a CSV (map places) and, in the next question, a JSON log (agent decisions).

| | Hand-coded ([`usl/hand_coded_join.py`](../../usl/hand_coded_join.py)) | Through the USL ([`05_queries.sql`](../../usl/sql/05_queries.sql)) |
|---|---|---|
| What you write | 42 lines of Python | 1 SQL statement of three joins |
| Access methods you must know | JDBC for the lakehouse, `csv` for the file | none; everything is a table |
| Type handling | by hand: strings to floats, JSON in `metadata_json` parsed with `json` and a regex | declared once in the DDL, checked at activation |
| NULL and missing rows | silently skipped inside loops | declared (`NOT NULL`, keys) and checked |
| Result | 4 rows | the same 4 rows |
| Wall-clock for one run | 11.7 s | about 20 s including starting a JVM and connecting |

We are **not** claiming the USL is faster at run time. In a one-off script it was slower, because each query pays for the federated engine. The value
is elsewhere.

## Where the time went

Building the USL took us longer than writing the 42-line script. That is the honest cost: the USL DDL is 49 lines and the activation queries are 58, so
the first question cost more than the script did. Most of that was not the work itself but discovering syntax the platform download does not document
(see [2c](2c-product-requirement.md)): we found `COMPILE USL … DEPLOY`, `ACTIVATE USL TABLE` and `REGISTER DQ` by reading the engine's parser, and
learned the rules (multi-table DDL needs newline-separated statements ending in `;`, local files must sit under `customer-data/shared`) from error
messages. *Estimate:* with documented syntax, the same build is a 30–45 minute job, which is the number we use below.

The saving appears from the second consumer onward:

| Consumer of the same three sources | Hand-coded: new glue | With the USL |
|---|---|---|
| "Which model made each decision?" | another parser for the JSON log, plus a join key we invent | `SELECT … FROM agent_decision` (one line) |
| "Which intentions have no reachable screenshot?" | a new script that re-implements the entity→evidence join | a data-quality rule (one statement) |
| A teammate's dashboard | they re-write the glue, and may disagree about what "verified place" means | they query `saved_place`; the definition lives in one place |
| A new source (say, opening hours) | change every script that needs it | add a column to one activation query |

*Estimate:* each additional question that crosses sources costs 20–40 minutes by hand (write the access code, the join, the casts, check it
against the others) and about 2 minutes through the USL. Over the five questions we asked in this project that is about 2.3 hours of hand-coding avoided (5 × 28 minutes) for about 45 minutes of setup, roughly
1.5 hours net. The break-even is the second question. We did not time ourselves with a stopwatch; treat these as estimates, not
measurements.

## What the USL caught that glue would not

The hand-coded join prints four rows and looks fine. The USL rule `active_intention_has_a_screenshot` ran across the same tables and reported two
open intentions that reach **zero** screenshots ([RUN.md §4](../../usl/results/RUN.md)). Nothing in our application code ever asks that question:
the Pingo app links screenshots to intentions only through named entities, and two images had none. The defect was real, and we found it only because
the relationship was declared once and a rule could be written over it. That is time saved in the form of a bug found before a judge found it.

## What it did not save

- It did not remove the need to understand the sources. We still had to know that the map directory's `osm_id` equals the number inside
  `entities.metadata_json`.
- It did not replace our application's repository code. Pingo's agents still read `recall_data.app` directly, because the USL is a read-side layer and the agents
  also write (evidence, intentions, reminders).
- It does not help a one-off script. If we only ever asked one question, the 42 lines would have been the right answer.
