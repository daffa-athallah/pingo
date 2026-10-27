-- Source 1: recall_data.app is already a native Iceberg lakehouse namespace (Pingo's memory). Nothing to register.
-- Sources 2 and 3 are onboarded as Lightning filestore tables. The files are produced by backend/scripts/usl_export.py and copied under the
-- driver's local file-system root (/home/zetaris/customer-data/shared).
CREATE LIGHTNING DATABASE pingo_sources DESCRIBE BY "Pingo reference sources, map place directory and agent decision log" OPTIONS ()
----
CREATE LIGHTNING FILESTORE TABLE place_directory FROM pingo_sources
FORMAT csv
OPTIONS (path "/home/zetaris/customer-data/shared/pingo/place_directory", header "true")
----
CREATE LIGHTNING FILESTORE TABLE agent_trace FROM pingo_sources
FORMAT json
OPTIONS (path "/home/zetaris/customer-data/shared/pingo/agent_trace", multiLine "true")
