# 2c · Making the USL stronger: a product requirement for Zetaris

**Audience:** the Zetaris product team. **Author's position:** a customer who built a three-source USL from the platform download, with no help, in
one session. Everything below is something we hit, with the evidence. Statements marked *verified* we reproduced; the rest is a proposal.

## Summary

The USL is the right idea and the engine under it is good. The error that said exactly how to fix a NOT NULL mismatch (it even suggested
`COALESCE(loop_id, '')` and a complete corrected SELECT) was the best developer experience in the whole build. The weakness is the **path to a first
USL**: it is undocumented, partly silent when it goes wrong, and at least one failure loses data without saying so. Fix those three things and a
customer goes from "I read your class files" to a working USL in under an hour.

## Problem 1 · A customer cannot discover how to build a USL

*Verified.* The platform download documents install, sample data and JDBC. It does not mention the USL. The commands exist (`COMPILE USL`,
`ACTIVATE USL TABLE`, `LOAD USL`, `REGISTER DQ`, `RUN DQ`, `SHOW DQ`), but we found them only by reading the parser's class files in the driver
image and then probing it with trial statements.

**Requirement R1.** Ship a USL guide in the platform download with one worked example (three sources, five tables, activation, one rule) that runs
against the bundled sample data (`NY_TAXI`, `TPCDS_DB`). **Acceptance:** a new user who has only the README builds and queries a USL in under 60
minutes without reading source or class files.

## Problem 2 · Failures are silent or point at the wrong cause

| What we did (all verified) | What happened | What it should do |
|---|---|---|
| `FORMAT json` over a 360-line JSON-lines file | Registered successfully and returned **1 row**. No warning. | Parse JSON lines, or fail with "multi-document JSON; set `multiLine` or provide an array". Silent data loss is the worst outcome in a data product. |
| Two `CREATE TABLE`s in one `DDL` separated by a space | `Invalid DDL statement. Please provide a valid CREATE TABLE statement…` | Say "multiple statements: separate with a newline and `;`" (that is the rule). |
| `NAMESPACE lightning.pingo` | `name space must be formed : lightning(.namespace)*` (it *looks* like it is) | Say "the second level must be `datasource` or `metastore`". |
| `COMPILE USL x NAMESPACE …` without `DEPLOY` | Returns the compiled JSON and persists **nothing**; `LOAD USL x` then says not existing. | State in the response that nothing was saved, or make `DEPLOY` the default. |
| `COMPILE USL NAMESPACE …` with no name | Stored a USL named `""` (an empty string). | Require a name. |
| A local file source outside the allowed folder | `Invalid file path to access` | Name the allowed root (`/home/zetaris/customer-data/shared`); we found it in `docker-compose.yml`. |
| `DESCRIBE BY "…: …"` with a colon | A rule about allowed characters | Show the offending character and the allowed set in one message (the current message does list the set, but not which character failed). |

**Requirement R2.** Every failure above returns a message that states the cause and the fix; no registration may succeed while reading fewer
rows than the file contains. **Acceptance:** each row of the table has a regression test; `SELECT count(*)` over a registered file equals the
file's record count, or the registration fails.

## Problem 3 · Data quality is a rule runner, not a quality state

*Verified.* `RUN DQ` returns total, valid and invalid counts. It does not keep history, so we cannot show "was this good yesterday?". The `SHOW` grammar
is narrow (`SHOW DQ ALL INVALID TABLE …` works; `SHOW DQ <rule> …` does not parse). Primary and foreign key constraints appear as "rules" in `LIST DQ`
but cannot be run or reported on like custom rules.

**Requirement R3.** Persist each DQ run (rule, table, time, total, valid, invalid, sample of invalid keys), expose it as a queryable system table
`lightning.metastore.<ns>.dq_runs`, and let key constraints run like any rule. **Acceptance:** after two runs, `SELECT * FROM dq_runs` shows both,
and a key violation appears in the same table as a custom-rule violation.

## Problem 4 · Building the USL is manual where the engine already knows

The engine already knows column types, keys it can profile, and (from our activation errors) which queries match which declared schema. We hand-wrote
every relationship and every activation query. For a customer with 30 tables that is the whole project.

**Requirement R4 (the headline feature).** `INFER USL`: given a set of sources, propose tables, keys, cross-source links with a confidence, quality rules
from profiling, and column lineage, as a *reviewable* proposal. Nothing is deployed until a person accepts it. **Acceptance:** on our three sources, it proposes the
three keys and two cross-source links we wrote by hand, flags the two intentions that violate "an open intention has a screenshot", and shows the lineage of
`saved_place.latitude`. A concrete example is below.

### Bonus · an example of the feature, and the USL it would produce

[`usl/mock/infer_usl.sql`](../../usl/mock/infer_usl.sql) is a mock (the feature does not exist). It contains:

```sql
INFER USL pingo_usl NAMESPACE lightning.metastore.pingo
FROM SOURCES (recall_data.app.*, pingo_sources.place_directory, pingo_sources.agent_trace)
WITH RELATIONSHIPS AUTO, SAMPLE 10000 ROWS, PROFILE QUALITY;
```

and the review output it would print: proposed tables, keys (with match percentages), two cross-source links with confidence (the OSM id inside
`entities.metadata_json` ↔ `place_directory.osm_id`; the decision text ↔ the intention title), quality rules from profiling (one of which our data
**violates**, as it really does today), and lineage for each column. The resulting USL is the same DDL our hand-built USL uses
([`02_usl_ddl.sql`](../../usl/sql/02_usl_ddl.sql)), so you can compare the proposal with what a person actually needed.

## Out of scope for this requirement

Access control, materialisation and cost-based federation: we did not exercise them, so we make no request about them.

## How we would measure success

| Metric | Today (our experience) | Target |
|---|---|---|
| Time from download to a queryable 3-source USL, documentation only | roughly 2 hours (our estimate), by reading the engine | under 1 hour |
| Silent wrong results found while building | 1 (JSON lines read as 1 row) | 0 |
| Failures whose message names the cause and the fix | 1 of the 7 above already does | all |
| Hand-written relationship and activation statements for 3 sources | 5 tables · 58 lines of activation SQL | reviewed, not written |
