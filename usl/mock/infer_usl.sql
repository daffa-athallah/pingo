-- MOCK. This is a proposal, not something Zetaris runs today. It shows the feature described in docs/usl/2c-product-requirement.md.
-- The "resulting USL" below is what we would want it to produce for the three Pingo sources, so the requirement can be judged against a concrete output.

INFER USL pingo_usl NAMESPACE lightning.metastore.pingo
FROM SOURCES (recall_data.app.*, pingo_sources.place_directory, pingo_sources.agent_trace)
WITH RELATIONSHIPS AUTO, SAMPLE 10000 ROWS, PROFILE QUALITY;

-- Mocked output: a reviewable proposal. Nothing is deployed until a person accepts it (ACCEPT INFERRED USL pingo_usl).
--
-- PROPOSED TABLES           (from)                              keys inferred                       
--   saved_intention          recall_data.app.open_loops          PK loop_id (unique, 100% non-null)
--   saved_place              recall_data.app.entities            PK entity_id
--   intention_place          recall_data.app.loop_entities       FK loop_id -> saved_intention (100% match)
--                                                                FK entity_id -> saved_place    (100% match)
--   reminder                 recall_data.app.notifications       FK loop_id -> saved_intention (100% match)
--   agent_decision           pingo_sources.agent_trace           (no key)
--
-- PROPOSED CROSS-SOURCE LINKS (needs confirmation)
--   saved_place.metadata_json.$.location_id  ~  place_directory.osm_id     confidence 0.94  (illustrative: sampled ids match after stripping "osm:node:")
--   agent_decision.summary ~ saved_intention.title                          confidence 0.7   (illustrative: the decision text quotes the title)
--
-- PROPOSED QUALITY RULES (from profiling)
--   saved_intention.confidence between 0 and 1                              (observed range reported here)
--   saved_place.latitude between -90 and 90                                 (observed -37.93 to 59.40)
--   agent_decision.model and provider are both null or both set            (observed in 100% of rows)
--   saved_intention.screenshot_count >= 1 for open intentions               VIOLATED by 2 of 24 rows
--
-- PROPOSED LINEAGE (every USL column knows where it comes from)
--   saved_place.latitude  <-  COALESCE(place_directory.latitude, entities.metadata_json.$.latitude)

-- Resulting USL (what ACCEPT would deploy), in today's syntax:
COMPILE OR REPLACE USL pingo_usl DEPLOY NAMESPACE lightning.metastore.pingo DDL
CREATE TABLE saved_intention (loop_id STRING PRIMARY KEY, title STRING NOT NULL, status STRING NOT NULL, screenshot_count INT);
CREATE TABLE saved_place (entity_id STRING PRIMARY KEY, name STRING NOT NULL, latitude DOUBLE, longitude DOUBLE, location_verified BOOLEAN);
CREATE TABLE intention_place (loop_id STRING NOT NULL, entity_id STRING NOT NULL,
  FOREIGN KEY (loop_id) REFERENCES saved_intention(loop_id), FOREIGN KEY (entity_id) REFERENCES saved_place(entity_id));
