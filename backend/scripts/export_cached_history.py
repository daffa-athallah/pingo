#!/usr/bin/env python3
"""Export saved run history, without model calls, database access or invented decisions."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.runs_api import latest_curated


def export():
    records = []
    for saved in latest_curated():
        record = deepcopy(saved)
        record.update(provenance='recorded', workspace='sample', cached=True,
                      original_provenance=saved['provenance'], original_workspace=saved['workspace'])
        record['recording_note'] = 'Cached result of an earlier model run. Reading history does not run an agent or model again.'
        records.append(record)
    if not records:
        raise RuntimeError('No saved history exists; refusing to invent sample decisions.')
    target = ROOT / 'backend/demo/history.json'
    target.write_text(json.dumps({'cached_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                 'source': 'saved local run reports', 'records': records}, indent=2, ensure_ascii=False) + '\n')
    print(f'Exported {len(records)} existing run records to {target.relative_to(ROOT)}; no inference or database calls.')


if __name__ == '__main__':
    export()
