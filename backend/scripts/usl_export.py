"""Export the two non-Zetaris sources of the Pingo Unified Semantic Layer to files Zetaris can onboard.

  place_directory.csv  what the Location Agent's map lookups returned (OpenStreetMap), flattened from the geocode cache
  agent_trace.json     the agents' decision log (logs/trace.jsonl) as one JSON array, with sanitized model receipts

Run: backend/.venv/bin/python backend/scripts/usl_export.py   (writes usl/data/*)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'usl/data'
GEOCODE = ROOT / 'backend/runtime/geocode'
TRACE = ROOT / 'logs/trace.jsonl'
FIELDS = ['osm_type', 'osm_id', 'name', 'category', 'type', 'house_number', 'road', 'suburb', 'city', 'state', 'postcode', 'country',
          'latitude', 'longitude', 'importance', 'display_name']


def place_rows():
    seen = {}
    sources = [item for path in sorted(GEOCODE.glob('*.json')) for item in json.loads(path.read_text()).get('results', [])]
    try:
        sources += lookup_verified_places()
    except Exception as error:  # the cache alone is still a valid source
        print('OSM lookup skipped:', type(error).__name__)
    for item in sources:
        if not isinstance(item, dict) or 'osm_id' not in item:
            continue
        address = item.get('address') or {}
        key = (item['osm_type'], item['osm_id'])
        seen[key] = {
            'osm_type': item['osm_type'], 'osm_id': item['osm_id'], 'name': item.get('name') or '', 'category': item.get('category') or '',
            'type': item.get('type') or '', 'house_number': address.get('house_number') or '', 'road': address.get('road') or '',
            'suburb': address.get('suburb') or '', 'city': address.get('city') or address.get('town') or '', 'state': address.get('state') or '',
            'postcode': address.get('postcode') or '', 'country': address.get('country') or '', 'latitude': item['lat'], 'longitude': item['lon'],
            'importance': item.get('importance') or '', 'display_name': item.get('display_name') or ''}
    return list(seen.values())


def lookup_verified_places():
    """OpenStreetMap rows for every place the agents verified, fetched by OSM id in one polite batch (Nominatim /lookup, identifying User-Agent)."""
    import re
    import sys
    import urllib.parse
    import urllib.request
    sys.path.insert(0, str(ROOT / 'backend/scripts'))
    from real_env import load_env, real_repository
    load_env()
    with real_repository() as repo:
        rows = repo.connection.query(f"SELECT metadata_json FROM {repo._table('entities')} WHERE metadata_json LIKE '%osm:%'", ())
    ids = sorted({f"{m.group(1)[0].upper()}{m.group(2)}" for (meta,) in rows
                  for m in [re.search(r'"location_id":"osm:(node|way|relation):(\d+)"', meta)] if m})
    found = []
    for start in range(0, len(ids), 40):
        query = urllib.parse.urlencode({'osm_ids': ','.join(ids[start:start + 40]), 'format': 'jsonv2', 'addressdetails': 1})
        request = urllib.request.Request('https://nominatim.openstreetmap.org/lookup?' + query, headers={'User-Agent': 'Pingo-Recall-hackathon/1.0 (usl export)'})
        with urllib.request.urlopen(request, timeout=30) as response:
            found.extend(json.loads(response.read()))
    return found


def trace_rows():
    keep = ('timestamp', 'trace_id', 'agent_name', 'action', 'input_summary', 'output_summary', 'target_agent', 'confidence', 'retry_count', 'status',
            'provenance', 'workspace', 'model', 'provider')
    for line in TRACE.read_text().splitlines():
        if 'grafal' in line.lower():  # the person asked for everything about this place to be removed from Zetaris
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        yield {key: row.get(key) for key in keep}


def main():
    (OUT / 'place_directory').mkdir(parents=True, exist_ok=True)
    (OUT / 'agent_trace').mkdir(parents=True, exist_ok=True)
    places = place_rows()
    with open(OUT / 'place_directory/place_directory.csv', 'w', newline='') as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(places)
    rows = list(trace_rows())
    (OUT / 'agent_trace/agent_trace.json').write_text(json.dumps(rows, ensure_ascii=False, indent=0))
    print(f'place_directory.csv: {len(places)} places; agent_trace.json: {len(rows)} events')


if __name__ == '__main__':
    main()
