-- The Pingo Unified Semantic Layer (USL): five logical tables, one vocabulary over three physical sources.
-- Deployed with:  COMPILE OR REPLACE USL pingo_usl DEPLOY NAMESPACE lightning.metastore.pingo DDL <this file>
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
