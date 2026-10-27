-- Source 1 · recall_data.app (Iceberg lakehouse)
SELECT 'evidence' AS table_name, count(*) AS rows FROM recall_data.app.evidence UNION ALL SELECT 'entities', count(*) FROM recall_data.app.entities UNION ALL SELECT 'open_loops', count(*) FROM recall_data.app.open_loops UNION ALL SELECT 'loop_entities', count(*) FROM recall_data.app.loop_entities UNION ALL SELECT 'notifications', count(*) FROM recall_data.app.notifications
----
SELECT status, count(*) AS intentions FROM recall_data.app.open_loops GROUP BY status ORDER BY intentions DESC
----
SELECT domain, count(*) AS screenshots, sum(CASE WHEN sensitive = true THEN 1 ELSE 0 END) AS sensitive FROM recall_data.app.evidence GROUP BY domain ORDER BY screenshots DESC
----
-- Source 2 · pingo_sources.place_directory (CSV filestore, OpenStreetMap)
SELECT count(*) AS places, count(DISTINCT suburb) AS suburbs, min(CAST(latitude AS DOUBLE)) AS min_lat, max(CAST(latitude AS DOUBLE)) AS max_lat FROM pingo_sources.place_directory
----
SELECT suburb, count(*) AS places FROM pingo_sources.place_directory WHERE suburb IS NOT NULL GROUP BY suburb ORDER BY places DESC, suburb LIMIT 5
----
SELECT name, road, suburb, postcode, latitude, longitude FROM pingo_sources.place_directory WHERE name IS NOT NULL AND name <> '' ORDER BY name LIMIT 5
----
-- Source 3 · pingo_sources.agent_trace (JSON filestore, the agents' decision log)
SELECT agent_name, count(*) AS events FROM pingo_sources.agent_trace GROUP BY agent_name ORDER BY events DESC
----
SELECT workspace, provenance, count(DISTINCT trace_id) AS runs, count(*) AS events FROM pingo_sources.agent_trace GROUP BY workspace, provenance ORDER BY runs DESC
----
SELECT agent_name, provider, model, count(*) AS model_calls FROM pingo_sources.agent_trace WHERE model IS NOT NULL GROUP BY agent_name, provider, model ORDER BY model_calls DESC
----
-- The USL is active · every query below reads only lightning.metastore.pingo.pingo_usl.*, never a physical source
SELECT i.title AS intention, p.name AS place, p.suburb, p.latitude, p.longitude FROM lightning.metastore.pingo.pingo_usl.intention_place ip JOIN lightning.metastore.pingo.pingo_usl.saved_intention i ON i.loop_id = ip.loop_id JOIN lightning.metastore.pingo.pingo_usl.saved_place p ON p.entity_id = ip.entity_id WHERE p.location_verified = true AND i.status IN ('OPEN', 'ACTIVE') ORDER BY p.name
----
SELECT agent_name, provider, model, count(*) AS model_calls FROM lightning.metastore.pingo.pingo_usl.agent_decision WHERE model IS NOT NULL GROUP BY agent_name, provider, model ORDER BY model_calls DESC
----
SELECT i.title AS intention, i.status, i.screenshot_count, d.agent_name, d.action, d.model FROM lightning.metastore.pingo.pingo_usl.saved_intention i JOIN lightning.metastore.pingo.pingo_usl.agent_decision d ON d.loop_title = i.title WHERE d.action IN ('CREATE', 'ATTACH', 'STATE') ORDER BY i.updated_at DESC LIMIT 6
