# Pingo USL · build and verification run

Run at 2026-10-27T08:04:42+00:00. Every output below is the platform's own response.

## 1. Onboard the data sources

### Source 1: recall_data.app is already a native Iceberg lakehouse namespace (Pingo's memory). Nothing to register. Sources 2 and 3 are onboarded as Lightning filestore tables. The files are produced by backend/scripts/usl_export.py and copied under the driver's local file-system root (/home/zetaris/customer-data/shared).

```sql
CREATE LIGHTNING DATABASE pingo_sources DESCRIBE BY "Pingo reference sources, map place directory and agent decision log" OPTIONS ()
```

**SKIPPED (already exists)**

### CREATE LIGHTNING FILESTORE TABLE place_directory FROM pingo_sources

```sql
CREATE LIGHTNING FILESTORE TABLE place_directory FROM pingo_sources
FORMAT csv
OPTIONS (path "/home/zetaris/customer-data/shared/pingo/place_directory", header "true")
```

**SKIPPED (already exists)**

### CREATE LIGHTNING FILESTORE TABLE agent_trace FROM pingo_sources

```sql
CREATE LIGHTNING FILESTORE TABLE agent_trace FROM pingo_sources
FORMAT json
OPTIONS (path "/home/zetaris/customer-data/shared/pingo/agent_trace", multiLine "true")
```

**SKIPPED (already exists)**

### Verify each source is operable

### Source check

```sql
SELECT count(*) AS rows FROM recall_data.app.evidence
```

**OK** · 1 rows
| rows |
|---|
| 42 |

### Source check

```sql
SELECT count(*) AS rows FROM pingo_sources.place_directory
```

**OK** · 1 rows
| rows |
|---|
| 30 |

### Source check

```sql
SELECT count(*) AS rows FROM pingo_sources.agent_trace
```

**OK** · 1 rows
| rows |
|---|
| 349 |

## 2. Compile and deploy the USL

### Compile and deploy (DDL in usl/sql/02_usl_ddl.sql)

```sql
COMPILE OR REPLACE USL pingo_usl DEPLOY NAMESPACE lightning.metastore.pingo DDL
CREATE TABLE saved_intention (
  loop_id STRING PRIMARY KEY,
  title STRING NOT NULL,
  domain STRING,
  status STRING NOT NULL,
  confidence DOUBLE,
  created_at STRING,
  updated_at STRING,
  screenshot_count INT
);
CREATE TABLE saved_place (
  entity_id STRING PRIMARY KEY,
  name STRING NOT NULL,
  entity_type STRING,
  domain STRING,
  osm_id STRING,
  address STRING,
  suburb STRING,
  latitude DOUBLE,
  longitude DOUBLE,
  location_verified BOOLEAN
);
CREATE TABLE intention_place (
  loop_id STRING NOT NULL,
  entity_id STRING NOT NULL,
  relationship STRING,
  FOREIGN KEY (loop_id) REFERENCES saved_intention(loop_id),
  FOREIGN KEY (entity_id) REFERENCES saved_place(entity_id)
);
CREATE TABLE reminder (
  notification_id STRING PRIMARY KEY,
  loop_id STRING NOT NULL,
  run_id STRING,
  created_at STRING,
  FOREIGN KEY (loop_id) REFERENCES saved_intention(loop_id)
);
CREATE TABLE agent_decision (
  trace_id STRING NOT NULL,
  decided_at STRING,
  agent_name STRING NOT NULL,
  action STRING NOT NULL,
  provider STRING,
  model STRING,
  status STRING,
  summary STRING,
  loop_title STRING
);
```

**OK** · 1 rows
```
{"namespace":["metastore","pingo"],"name":"pingo_usl","tables":[{"name":"saved_intention","columnSpecs":[{"name":"loop_id","dataType":"\"string\"","primaryKe...
```

### The USL tables

```sql
SHOW NAMESPACES OR TABLES IN lightning.metastore.pingo.pingo_usl
```

**OK** · 5 rows
| name | type | usl_id | count | activated |
|---|---|---|---|---|
| agent_decision | table |  | 0 | False |
| intention_place | table |  | 0 | False |
| reminder | table |  | 0 | False |
| saved_intention | table |  | 0 | False |
| saved_place | table |  | 0 | False |

## 3. Activate: bind each logical table to the physical sources

### ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.saved_place AS

```sql
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.saved_place AS
SELECT e.entity_id,
       COALESCE(e.name, '') AS name,
       e.entity_type,
       e.domain,
       regexp_extract(get_json_object(e.metadata_json, '$.location_id'), 'osm:([a-z]+):([0-9]+)', 2) AS osm_id,
       d.display_name AS address,
       d.suburb,
       CAST(COALESCE(d.latitude, get_json_object(e.metadata_json, '$.latitude')) AS DOUBLE) AS latitude,
       CAST(COALESCE(d.longitude, get_json_object(e.metadata_json, '$.longitude')) AS DOUBLE) AS longitude,
       COALESCE(get_json_object(e.metadata_json, '$.location_verified') = 'true', false) AS location_verified
FROM recall_data.app.entities e
LEFT JOIN pingo_sources.place_directory d
  ON CAST(d.osm_id AS STRING) = regexp_extract(get_json_object(e.metadata_json, '$.location_id'), 'osm:([a-z]+):([0-9]+)', 2)
```

**OK** · 1 rows
| registered |
|---|
| {"name":"saved_place","query":"SELECT e.entity_id,\n       COALESCE(e.name, '') AS name,\n       e.entity_type,\n       e.domain,\n       regexp_extract(get_... |

### ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS

```sql
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS
SELECT l.loop_id,
       COALESCE(l.title, '') AS title,
       l.domain,
       COALESCE(l.status, 'UNKNOWN') AS status,
       CAST(l.confidence AS DOUBLE) AS confidence,
       l.created_at,
       l.updated_at,
       CAST(COUNT(DISTINCT ee.evidence_id) AS INT) AS screenshot_count
FROM recall_data.app.open_loops l
LEFT JOIN recall_data.app.loop_entities le ON le.loop_id = l.loop_id
LEFT JOIN recall_data.app.evidence_entities ee ON ee.entity_id = le.entity_id
GROUP BY l.loop_id, l.title, l.domain, l.status, l.confidence, l.created_at, l.updated_at
```

**OK** · 1 rows
| registered |
|---|
| {"name":"saved_intention","query":"SELECT l.loop_id,\n       COALESCE(l.title, '') AS title,\n       l.domain,\n       COALESCE(l.status, 'UNKNOWN') AS statu... |

### ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.intention_place AS

```sql
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.intention_place AS
SELECT COALESCE(le.loop_id, '') AS loop_id, COALESCE(le.entity_id, '') AS entity_id, le.relationship
FROM recall_data.app.loop_entities le
JOIN recall_data.app.open_loops l ON l.loop_id = le.loop_id
JOIN recall_data.app.entities e ON e.entity_id = le.entity_id
```

**OK** · 1 rows
| registered |
|---|
| {"name":"intention_place","query":"SELECT COALESCE(le.loop_id, '') AS loop_id, COALESCE(le.entity_id, '') AS entity_id, le.relationship\nFROM recall_data.app... |

### ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.reminder AS

```sql
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.reminder AS
SELECT n.notification_id,
       COALESCE(n.loop_id, '') AS loop_id,
       get_json_object(n.payload_json, '$.run_id') AS run_id,
       n.created_at
FROM recall_data.app.notifications n
```

**OK** · 1 rows
| registered |
|---|
| {"name":"reminder","query":"SELECT n.notification_id,\n       COALESCE(n.loop_id, '') AS loop_id,\n       get_json_object(n.payload_json, '$.run_id') AS run_... |

### ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.agent_decision AS

```sql
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.agent_decision AS
SELECT COALESCE(t.trace_id, '') AS trace_id,
       t.timestamp AS decided_at,
       COALESCE(t.agent_name, '') AS agent_name,
       COALESCE(t.action, '') AS action,
       t.provider,
       t.model,
       t.status,
       t.output_summary AS summary,
       NULLIF(regexp_extract(t.output_summary, 'Loop "(.*)":', 1), '') AS loop_title
FROM pingo_sources.agent_trace t
WHERE t.workspace = 'canonical'
```

**OK** · 1 rows
| registered |
|---|
| {"name":"agent_decision","query":"SELECT COALESCE(t.trace_id, '') AS trace_id,\n       t.timestamp AS decided_at,\n       COALESCE(t.agent_name, '') AS agent... |

## 4. Data quality

### REGISTER DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl

```sql
REGISTER DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl.saved_place AS location_verified = false OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
```

**OK** · 1 rows
```
{"namespace":["metastore","pingo"],"name":"pingo_usl","tables":[{"name":"saved_intention","columnSpecs":[{"name":"loop_id","dataType":"\"string\"","primaryKe...
```

### REGISTER DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_in

```sql
REGISTER DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
```

**OK** · 1 rows
```
{"namespace":["metastore","pingo"],"name":"pingo_usl","tables":[{"name":"saved_place","columnSpecs":[{"name":"entity_id","dataType":"\"string\"","primaryKey"...
```

### REGISTER DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_deci

```sql
REGISTER DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_decision AS (model IS NULL AND provider IS NULL) OR (model IS NOT NULL AND provider IS NOT NULL)
```

**OK** · 1 rows
```
{"namespace":["metastore","pingo"],"name":"pingo_usl","tables":[{"name":"saved_place","columnSpecs":[{"name":"entity_id","dataType":"\"string\"","primaryKey"...
```

### REGISTER DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.sa

```sql
REGISTER DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS status NOT IN ('OPEN', 'ACTIVE') OR screenshot_count >= 1
```

**OK** · 1 rows
```
{"namespace":["metastore","pingo"],"name":"pingo_usl","tables":[{"name":"saved_place","columnSpecs":[{"name":"entity_id","dataType":"\"string\"","primaryKey"...
```

### RUN DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl.save

```sql
RUN DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl.saved_place
```

**OK** · 1 rows
| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| verified_place_has_valid_coordinates | saved_place | Custom Data Quality | 72 | 72 | 0 |

### RUN DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_intenti

```sql
RUN DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_intention
```

**OK** · 1 rows
| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| confidence_is_a_probability | saved_intention | Custom Data Quality | 42 | 42 | 0 |

### RUN DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_decision

```sql
RUN DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_decision
```

**OK** · 1 rows
| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| model_receipt_is_complete | agent_decision | Custom Data Quality | 156 | 156 | 0 |

### RUN DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.saved_i

```sql
RUN DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.saved_intention
```

**OK** · 1 rows
| name | table | type | total_record | valid_record | invalid_record |
|---|---|---|---|---|---|
| active_intention_has_a_screenshot | saved_intention | Custom Data Quality | 42 | 40 | 2 |

### SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_intention

```sql
SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_intention
```

**OK** · 2 rows
| records |
|---|
| {"loop_id":"loop_43f106a00bbc","title":"Interested in jogging/running outdoors","domain":"health","status":"ACTIVE","confidence":0.7,"created_at":"2026-10-27... |
| {"loop_id":"loop_509c7dd016cc","title":"Interested in fried rice with fried egg dish","domain":"food","status":"ACTIVE","confidence":0.85,"created_at":"2026-... |

### SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_place

```sql
SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_place
```

**OK** · 0 rows

### Rules registered on the USL (custom + key constraints)

```sql
LIST DQ USL lightning.metastore.pingo.pingo_usl
```

**OK** · 10 rows
| name | table | type | expression |
|---|---|---|---|
| entity_id | saved_place | Primary key constraints |  |
| verified_place_has_valid_coordinates | saved_place | Custom Data Quality | location_verified = false OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) |
| loop_id | saved_intention | Primary key constraints |  |
| confidence_is_a_probability | saved_intention | Custom Data Quality | confidence IS NULL OR (confidence >= 0 AND confidence <= 1) |
| active_intention_has_a_screenshot | saved_intention | Custom Data Quality | status NOT IN ('OPEN', 'ACTIVE') OR screenshot_count >= 1 |
| loop_id | intention_place | Foreign key constraints |  |
| entity_id | intention_place | Foreign key constraints |  |
| notification_id | reminder | Primary key constraints |  |
| loop_id | reminder | Foreign key constraints |  |
| model_receipt_is_complete | agent_decision | Custom Data Quality | (model IS NULL AND provider IS NULL) OR (model IS NOT NULL AND provider IS NOT NULL) |

## 5. Queries

### Source 1 · recall_data.app (Iceberg lakehouse)

```sql
SELECT 'evidence' AS table_name, count(*) AS rows FROM recall_data.app.evidence UNION ALL SELECT 'entities', count(*) FROM recall_data.app.entities UNION ALL SELECT 'open_loops', count(*) FROM recall_data.app.open_loops UNION ALL SELECT 'loop_entities', count(*) FROM recall_data.app.loop_entities UNION ALL SELECT 'notifications', count(*) FROM recall_data.app.notifications
```

**OK** · 5 rows
| table_name | rows |
|---|---|
| evidence | 42 |
| entities | 72 |
| open_loops | 42 |
| loop_entities | 93 |
| notifications | 2 |

### SELECT status, count(*) AS intentions FROM recall_data.app.open_loops GROUP BY s

```sql
SELECT status, count(*) AS intentions FROM recall_data.app.open_loops GROUP BY status ORDER BY intentions DESC
```

**OK** · 3 rows
| status | intentions |
|---|---|
| INVALIDATED | 18 |
| OPEN | 18 |
| ACTIVE | 6 |

### SELECT domain, count(*) AS screenshots, sum(CASE WHEN sensitive = true THEN 1 EL

```sql
SELECT domain, count(*) AS screenshots, sum(CASE WHEN sensitive = true THEN 1 ELSE 0 END) AS sensitive FROM recall_data.app.evidence GROUP BY domain ORDER BY screenshots DESC
```

**OK** · 8 rows
| domain | screenshots | sensitive |
|---|---|---|
| shopping | 15 | 0 |
| food | 12 | 0 |
| health | 5 | 0 |
| travel | 4 | 0 |
| event | 3 | 0 |
| beauty | 1 | 0 |
| social | 1 | 0 |
| other | 1 | 0 |

### Source 2 · pingo_sources.place_directory (CSV filestore, OpenStreetMap)

```sql
SELECT count(*) AS places, count(DISTINCT suburb) AS suburbs, min(CAST(latitude AS DOUBLE)) AS min_lat, max(CAST(latitude AS DOUBLE)) AS max_lat FROM pingo_sources.place_directory
```

**OK** · 1 rows
| places | suburbs | min_lat | max_lat |
|---|---|---|---|
| 30 | 15 | -37.9277623 | 59.40292 |

### SELECT suburb, count(*) AS places FROM pingo_sources.place_directory WHERE subur

```sql
SELECT suburb, count(*) AS places FROM pingo_sources.place_directory WHERE suburb IS NOT NULL GROUP BY suburb ORDER BY places DESC, suburb LIMIT 5
```

**OK** · 5 rows
| suburb | places |
|---|---|
| Clayton | 4 |
| Carlton | 3 |
| Campbellfield | 2 |
| Melbourne | 2 |
| Brunswick | 1 |

### SELECT name, road, suburb, postcode, latitude, longitude FROM pingo_sources.plac

```sql
SELECT name, road, suburb, postcode, latitude, longitude FROM pingo_sources.place_directory WHERE name IS NOT NULL AND name <> '' ORDER BY name LIMIT 5
```

**OK** · 5 rows
| name | road | suburb | postcode | latitude | longitude |
|---|---|---|---|---|---|
| Clayton |  |  | 30525 | 34.8781479 | -83.4009933 |
| Clayton |  |  | 63105 | 38.6504352 | -90.3362473 |
| Clayton |  |  | 94517 | 37.9411668 | -121.9357878 |
| Clayton County |  |  |  | 42.8547706 | -91.3667151 |
| Clayton County |  |  |  | 33.5204959 | -84.3591713 |

### Source 3 · pingo_sources.agent_trace (JSON filestore, the agents' decision log)

```sql
SELECT agent_name, count(*) AS events FROM pingo_sources.agent_trace GROUP BY agent_name ORDER BY events DESC
```

**OK** · 11 rows
| agent_name | events |
|---|---|
| OPEN_LOOP | 108 |
| EVIDENCE | 65 |
| H-MEM | 38 |
| CRITIC | 27 |
| UPLOAD | 24 |
| RUN | 22 |
| REPOSITORY | 18 |
| ZETARIS | 14 |
| LOCATION | 14 |
| CONTEXT | 12 |
| CHECK_IN | 7 |

### SELECT workspace, provenance, count(DISTINCT trace_id) AS runs, count(*) AS even

```sql
SELECT workspace, provenance, count(DISTINCT trace_id) AS runs, count(*) AS events FROM pingo_sources.agent_trace GROUP BY workspace, provenance ORDER BY runs DESC
```

**OK** · 4 rows
| workspace | provenance | runs | events |
|---|---|---|---|
| canonical | live | 16 | 156 |
| sample | recorded | 8 | 108 |
| demo | live | 7 | 76 |
| sample | live | 1 | 9 |

### SELECT agent_name, provider, model, count(*) AS model_calls FROM pingo_sources.a

```sql
SELECT agent_name, provider, model, count(*) AS model_calls FROM pingo_sources.agent_trace WHERE model IS NOT NULL GROUP BY agent_name, provider, model ORDER BY model_calls DESC
```

**OK** · 5 rows
| agent_name | provider | model | model_calls |
|---|---|---|---|
| EVIDENCE | openai | gpt-4o-mini | 28 |
| CRITIC | nvidia | nvidia/nemotron-3-ultra-550b-a55b | 27 |
| OPEN_LOOP | nvidia | nvidia/nemotron-3-ultra-550b-a55b | 26 |
| CONTEXT | nvidia | nvidia/nemotron-3-ultra-550b-a55b | 12 |
| LOCATION | nvidia | nvidia/nemotron-3-ultra-550b-a55b | 1 |

### The USL is active · every query below reads only lightning.metastore.pingo.pingo_usl.*, never a physical source

```sql
SELECT i.title AS intention, p.name AS place, p.suburb, p.latitude, p.longitude FROM lightning.metastore.pingo.pingo_usl.intention_place ip JOIN lightning.metastore.pingo.pingo_usl.saved_intention i ON i.loop_id = ip.loop_id JOIN lightning.metastore.pingo.pingo_usl.saved_place p ON p.entity_id = ip.entity_id WHERE p.location_verified = true AND i.status IN ('OPEN', 'ACTIVE') ORDER BY p.name
```

**OK** · 4 rows
| intention | place | suburb | latitude | longitude |
|---|---|---|---|---|
| Researching Melbourne cheeseburger options | Easey’s | Collingwood | -37.7975407 | 144.9863556 |
| Researching Melbourne cheeseburger options | Gimlet | Melbourne | -37.8158796 | 144.9693073 |
| Researching Melbourne cheeseburger options | Juanita Peaches | Brunswick | -37.7740736 | 144.961712 |
| Researching Melbourne cheeseburger options | Slowpoke | Fitzroy | -37.802864 | 144.977535 |

### SELECT agent_name, provider, model, count(*) AS model_calls FROM lightning.metas

```sql
SELECT agent_name, provider, model, count(*) AS model_calls FROM lightning.metastore.pingo.pingo_usl.agent_decision WHERE model IS NOT NULL GROUP BY agent_name, provider, model ORDER BY model_calls DESC
```

**OK** · 2 rows
| agent_name | provider | model | model_calls |
|---|---|---|---|
| EVIDENCE | openai | gpt-4o-mini | 14 |
| OPEN_LOOP | nvidia | nvidia/nemotron-3-ultra-550b-a55b | 10 |

### SELECT i.title AS intention, i.status, i.screenshot_count, d.agent_name, d.actio

```sql
SELECT i.title AS intention, i.status, i.screenshot_count, d.agent_name, d.action, d.model FROM lightning.metastore.pingo.pingo_usl.saved_intention i JOIN lightning.metastore.pingo.pingo_usl.agent_decision d ON d.loop_title = i.title WHERE d.action IN ('CREATE', 'ATTACH', 'STATE') ORDER BY i.updated_at DESC LIMIT 6
```

**OK** · 6 rows
| intention | status | screenshot_count | agent_name | action | model |
|---|---|---|---|---|---|
| Interested in light pink ribbed halter neck tank top | OPEN | 1 | OPEN_LOOP | STATE |  |
| Interested in fried rice with fried egg dish | ACTIVE | 0 | OPEN_LOOP | STATE |  |
| Interested in fried rice with fried egg dish | ACTIVE | 0 | OPEN_LOOP | STATE |  |
| Interested in jogging/running outdoors | ACTIVE | 0 | OPEN_LOOP | STATE |  |
| Interested in jogging/running outdoors | ACTIVE | 0 | OPEN_LOOP | STATE |  |
| Interested in brown sporty sunglasses | OPEN | 1 | OPEN_LOOP | STATE |  |

