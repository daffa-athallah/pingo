-- Adds daily Check-in questions and answers. Apply once, after zetaris_schema_create.sql.
CREATE TABLE recall_data.app.check_ins (
  check_in_id STRING,
  day STRING,
  kind STRING,
  loop_id STRING,
  other_loop_id STRING,
  question_json STRING,
  status STRING,
  created_at STRING,
  response STRING,
  comment STRING,
  answered_at STRING
) USING iceberg;
