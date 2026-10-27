"""The same question as USL query 1, answered WITHOUT the USL: "which verified places does each open intention point at, with address coordinates?"

Three sources, three access methods, one hand-written join. Compare with the single SQL statement in usl/sql/05_queries.sql.
Run: backend/.venv/bin/python usl/hand_coded_join.py
"""
import csv
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/scripts'))
from real_env import load_env, real_repository  # noqa: E402

load_env()
started = time.time()
with real_repository() as repo:                                   # source 1: Iceberg lakehouse over JDBC, one query per table
    q = repo.connection.query
    ns = 'recall_data.app.'
    loops = {r[0]: r for r in q(f'SELECT loop_id, title, status FROM {ns}open_loops', ())}
    links = q(f'SELECT loop_id, entity_id FROM {ns}loop_entities', ())
    entities = {r[0]: r for r in q(f'SELECT entity_id, name, metadata_json FROM {ns}entities', ())}
with open(ROOT / 'usl/data/place_directory/place_directory.csv', newline='') as handle:   # source 2: CSV file
    directory = {row['osm_id']: row for row in csv.DictReader(handle)}
rows = []
for loop_id, entity_id in links:                                   # the join, by hand
    loop, entity = loops.get(loop_id), entities.get(entity_id)
    if not loop or not entity or loop[2] not in ('OPEN', 'ACTIVE'):
        continue
    try:
        meta = json.loads(entity[2] or '{}')
    except ValueError:
        continue
    match = re.search(r'osm:[a-z]+:(\d+)', meta.get('location_id', ''))
    place = directory.get(match.group(1)) if match else None
    if place and meta.get('location_verified') == 'true':
        rows.append((loop[1], entity[1], place['suburb'], float(place['latitude']), float(place['longitude'])))
for row in sorted(rows, key=lambda r: r[1]):
    print(row)
print(f'{len(rows)} rows in {time.time() - started:.1f}s')
