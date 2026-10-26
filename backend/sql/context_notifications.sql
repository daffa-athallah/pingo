-- Reviewed dry-run: additive application state only. No existing table changes.
-- Execute each statement separately through the existing Zetaris driver.
CREATE TABLE IF NOT EXISTS recall_data.app.context_evaluations (
  evaluation_id STRING,
  created_at STRING,
  payload_json STRING
) USING iceberg;

CREATE TABLE IF NOT EXISTS recall_data.app.notifications (
  notification_id STRING,
  loop_id STRING,
  created_at STRING,
  payload_json STRING
) USING iceberg;
