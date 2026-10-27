# Pingo × Zetaris: the Unified Semantic Layer

Pingo remembers what you saved and speaks up when something you saved becomes relevant. Zetaris is where that memory lives. This folder is the
**Unified Semantic Layer (USL)** we built on top of it: one vocabulary over three physically different sources, deployed on a real Zetaris
platform, with live queries and data-quality rules. Every number below comes from [`usl/results/RUN.md`](../../usl/results/RUN.md), the platform's own
output from a re-runnable build.

| Criterion | Where it is |
|---|---|
| 1a Use case and 3+ data sources | [Use case and sources](#1a-use-case-and-sources) |
| 1b 2–3 exploratory queries per source | [`usl/sql/05_queries.sql`](../../usl/sql/05_queries.sql), results in [RUN.md §5](../../usl/results/RUN.md) |
| 1c One USL, its DDL, active queries, a data-quality rule that runs | [The USL](#1c-the-usl) |
| 2a How the USL saved time versus hand-coding (bonus: hand-coded comparison) | [2a-time-saved.md](2a-time-saved.md) |
| 2b How the USL would or would not help our work (bonus: project and forecast) | [2b-would-it-help.md](2b-would-it-help.md) |
| 2c How to make the USL stronger, written as a PM requirement (bonus: example feature and USL) | [2c-product-requirement.md](2c-product-requirement.md) |

## 1a. Use case and sources

**Use case.** Pingo's agents decide whether to interrupt a person when they walk near something they saved. To explain *why* it spoke, a person (and a
judge) needs one answer that crosses three kinds of data: what they saved, where it is on the map, and which agent and model decided. Today those
live in three places with three access methods. The USL turns "show me every open intention, the verified place it points at, and who decided it"
into one query.

| # | Source | Kind in Zetaris | What it holds | Rows now |
|---|---|---|---|---|
| S1 | `recall_data.app` | Iceberg lakehouse (native) | Pingo's memory: evidence, entities, intentions, links, reminders, check-ins | 42 evidence · 72 entities · 42 intentions · 93 links · 2 reminders |
| S2 | `pingo_sources.place_directory` | Lightning filestore, **CSV** | OpenStreetMap place directory: address, suburb, coordinates for every place the Location Agent verified | 30 places |
| S3 | `pingo_sources.agent_trace` | Lightning filestore, **JSON** | The agents' decision log: agent, action, provider and model receipt, status | 349 events · 32 runs |

S2 and S3 are produced by [`usl_export.py`](../../backend/scripts/usl_export.py) and onboarded with `CREATE LIGHTNING FILESTORE TABLE`
([`01_sources.sql`](../../usl/sql/01_sources.sql)). S2 comes from OpenStreetMap (© OpenStreetMap contributors, ODbL) by OSM id, one polite batch request.
Anything that mentions a place the person asked us to remove is filtered out of S3 before it is copied.

### 1b. Exploratory queries

Three per source (nine in total), each recorded with its real output in [RUN.md](../../usl/results/RUN.md). Examples:

- **S1** `SELECT status, count(*) FROM recall_data.app.open_loops GROUP BY status` → 18 invalidated, 18 open, 6 active.
- **S2** `SELECT suburb, count(*) FROM pingo_sources.place_directory GROUP BY suburb` → Clayton 4, Carlton 3, …
- **S3** `SELECT agent_name, provider, model, count(*) FROM pingo_sources.agent_trace WHERE model IS NOT NULL GROUP BY …` → Evidence on `gpt-4o-mini`
  (openai), Open Loop on `nvidia/nemotron-3-ultra-550b-a55b` (nvidia).

Each source is first proven operable with a `count(*)` ([RUN.md §1](../../usl/results/RUN.md)).

## 1c. The USL

`pingo_usl` lives at `lightning.metastore.pingo`. Five logical tables, with primary and foreign keys, deployed from
[`02_usl_ddl.sql`](../../usl/sql/02_usl_ddl.sql) (the DDL; the compiled form is [`pingo_usl.compiled.json`](../../usl/results/pingo_usl.compiled.json)):

```text
saved_intention ──< intention_place >── saved_place          saved_place     = S1 entities  ⟕ S2 place_directory   (coordinates, address)
       │                                                      saved_intention = S1 open_loops ⟕ links ⟕ evidence    (screenshot count)
       └──< reminder                                          reminder        = S1 notifications
                                                              agent_decision  = S3 agent_trace   (loop_title parsed from the decision text)
```

Each table is *activated* with a query that binds it to the physical sources ([`03_activate.sql`](../../usl/sql/03_activate.sql)). The engine
checks the query against the declared types and even suggests the fix when they differ (for example, `COALESCE(loop_id, '')` for a NOT NULL column).

### The USL is active

Three queries that read only `lightning.metastore.pingo.pingo_usl.*`, never a physical source:

1. **Intention → verified place → address** (S1 ⟕ S2): the four places behind "Researching Melbourne cheeseburger options": Easey's (Collingwood),
   Gimlet (Melbourne), Juanita Peaches (Brunswick), Slowpoke (Fitzroy), each with real coordinates.
2. **Model routing per agent** (S3): Evidence → openai `gpt-4o-mini` (14 calls); Open Loop → nvidia `nemotron-3-ultra-550b-a55b` (10 calls), canonical workspace.
3. **Intention → how the agents decided it** (S1 ⟕ S3): each intention joined to the agent's `STATE`/`CREATE`/`ATTACH` decisions.

### Data quality

Four custom rules plus the key constraints, registered with `REGISTER DQ` and executed with `RUN DQ` ([`04_data_quality.sql`](../../usl/sql/04_data_quality.sql)):

| Rule | Table | Result |
|---|---|---|
| `verified_place_has_valid_coordinates` | saved_place | 72 / 72 valid |
| `confidence_is_a_probability` | saved_intention | 42 / 42 valid |
| `model_receipt_is_complete` | agent_decision | 156 / 156 valid (no model call is missing its provider) |
| `active_intention_has_a_screenshot` | saved_intention | **40 valid, 2 invalid** |

The last rule **found a real defect in Pingo**: two open intentions ("Interested in jogging/running outdoors", "Interested in fried rice with fried egg
dish") reach zero screenshots, because the Evidence Agent found no named entity in those images, and Pingo links screenshots to intentions only through
entities. The screenshot is stored, but invisible from its intention. We did not know until a USL rule asked the question across tables.
`SHOW DQ ALL INVALID TABLE …` lists the two offending rows ([RUN.md §4](../../usl/results/RUN.md)).

## Reproduce it

```sh
docker compose up -d                       # in the Zetaris platform folder; wait for ./verify.sh
backend/.venv/bin/python backend/scripts/usl_build.py
```

It exports S2 and S3, copies them under the driver's file root (`/home/zetaris/customer-data/shared/pingo`), onboards them, deploys and activates the
USL, registers and runs the rules, runs every query, and rewrites `usl/results/`. It is re-runnable, and it only ever **reads** `recall_data.app`.
The hand-coded comparison is [`usl/hand_coded_join.py`](../../usl/hand_coded_join.py).

## What we did not do

- The USL is not materialised to storage (`MATERIALIZE USL TABLE … TO STORAGE`): the queries read the sources live.
- The Pingo app itself still reads `recall_data.app` directly. The USL is the analytic and audit layer, not the agents' hot path (see
  [2b](2b-would-it-help.md)).
- S3 is a snapshot of the log taken when the build runs, not a stream. Re-run the build to refresh it.
