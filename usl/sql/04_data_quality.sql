-- Data quality rules on the USL. REGISTER stores a rule; RUN executes it over the live sources; SHOW lists failing (INVALID) rows.
REGISTER DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl.saved_place AS location_verified = false OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)
----
REGISTER DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
----
REGISTER DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_decision AS (model IS NULL AND provider IS NULL) OR (model IS NOT NULL AND provider IS NOT NULL)
----
REGISTER DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.saved_intention AS status NOT IN ('OPEN', 'ACTIVE') OR screenshot_count >= 1
----
RUN DQ verified_place_has_valid_coordinates TABLE lightning.metastore.pingo.pingo_usl.saved_place
----
RUN DQ confidence_is_a_probability TABLE lightning.metastore.pingo.pingo_usl.saved_intention
----
RUN DQ model_receipt_is_complete TABLE lightning.metastore.pingo.pingo_usl.agent_decision
----
RUN DQ active_intention_has_a_screenshot TABLE lightning.metastore.pingo.pingo_usl.saved_intention
----
-- A rule that catches real rows: an open intention whose screenshots cannot be reached through any named entity
SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_intention
----
SHOW DQ ALL INVALID TABLE lightning.metastore.pingo.pingo_usl.saved_place
