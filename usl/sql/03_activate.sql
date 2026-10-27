-- Each USL table is a logical table. ACTIVATE binds it to a query over the physical sources, so the USL reads them live and unifies them:
--   S1 recall_data.app        Iceberg lakehouse   Pingo's memory: intentions, entities, evidence, links, reminders
--   S2 pingo_sources.place_directory   CSV filestore    OpenStreetMap place directory (address, coordinates)
--   S3 pingo_sources.agent_trace       JSON filestore   the agents' decision log with sanitized model receipts
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
----
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
----
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.intention_place AS
SELECT COALESCE(le.loop_id, '') AS loop_id, COALESCE(le.entity_id, '') AS entity_id, le.relationship
FROM recall_data.app.loop_entities le
JOIN recall_data.app.open_loops l ON l.loop_id = le.loop_id
JOIN recall_data.app.entities e ON e.entity_id = le.entity_id
----
ACTIVATE USL TABLE lightning.metastore.pingo.pingo_usl.reminder AS
SELECT n.notification_id,
       COALESCE(n.loop_id, '') AS loop_id,
       get_json_object(n.payload_json, '$.run_id') AS run_id,
       n.created_at
FROM recall_data.app.notifications n
----
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
