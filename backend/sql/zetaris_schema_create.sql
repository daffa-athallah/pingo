-- Native schema verified after an approved dry-run and live storage probes.
-- Initial creation only: inspect existing objects before any rerun.
-- shared/ is the installed engine's permitted root inside its persistent volume.
-- Existing source databases and platform configuration must not be changed.
CREATE DATALAKE recall_data OPTIONS (
  storageType 'Local',
  storagePath '/home/zetaris/customer-data/shared/recall'
);

CREATE NAMESPACE IF NOT EXISTS recall_data.app;

CREATE TABLE recall_data.app.evidence (
  evidence_id STRING,
  source STRING,
  domain STRING,
  summary STRING,
  timestamp STRING,
  sensitive BOOLEAN,
  confidence STRING,
  image_ref STRING
) USING iceberg;

CREATE TABLE recall_data.app.entities (
  entity_id STRING,
  entity_type STRING,
  domain STRING,
  name STRING,
  category STRING,
  subcategory STRING,
  brand STRING,
  location_name STRING,
  city STRING,
  country STRING,
  metadata_json STRING
) USING iceberg;

CREATE TABLE recall_data.app.evidence_entities (
  evidence_id STRING,
  entity_id STRING,
  relationship STRING,
  confidence DOUBLE
) USING iceberg;

CREATE TABLE recall_data.app.open_loops (
  loop_id STRING,
  title STRING,
  domain STRING,
  status STRING,
  confidence DOUBLE,
  created_at STRING,
  updated_at STRING
) USING iceberg;

CREATE TABLE recall_data.app.loop_entities (
  loop_id STRING,
  entity_id STRING,
  relationship STRING,
  confidence DOUBLE
) USING iceberg;

CREATE TABLE recall_data.app.context_events (
  context_id STRING,
  context_type STRING,
  title STRING,
  occurs_at STRING,
  location_name STRING,
  city STRING,
  country STRING,
  metadata_json STRING
) USING iceberg;
