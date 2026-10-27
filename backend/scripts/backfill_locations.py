#!/usr/bin/env python3
"""One-off geocoding of saved places. Dry run by default; --apply writes entity metadata only.

Uses the same bounded location tool as screenshot upload, never re-invokes perception.
Public provider policy: https://operations.osmfoundation.org/policies/nominatim/
Run from one host only; do not schedule regular public-provider bulk jobs.
"""
import argparse
import asyncio
import json
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app import geocode
from backend.app.location_lookup import enrich_entities, retry_due, utcnow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='Persist lookup metadata; default only previews results')
    parser.add_argument('--force', action='store_true', help='Reconsider unresolved entity retry timestamps; provider cache/rate limit still apply')
    parser.add_argument('--limit', type=int, default=10, help='Small one-off batch, 1–20 entities')
    parser.add_argument('--entity-id', action='append', default=[], help='Limit to specified persisted IDs (repeatable)')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--report', type=Path, help='Optional report; use backend/runtime/ for local outputs')
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error('--limit must be 1–20')
    real_env.load_env(args.env_file)
    if not geocode.enabled():
        parser.error('Set RECALL_GEOCODE=on explicitly after reviewing the provider policy; SAMPLE_MODE must be false.')
    with real_repository() as repo:
        loops = repo.get_active_open_loops(limit=10000)
        wanted = {link.entity_id for link in repo.get_loop_entities([loop.loop_id for loop in loops])}
        if args.entity_id:
            wanted &= set(args.entity_id)
        todo = [entity for entity in repo.get_entities(sorted(wanted)) if geocode.eligible(entity)
                and (args.force or retry_due(entity, utcnow()))][:args.limit]
        rows = asyncio.run(enrich_entities(repo, todo, force=args.force, persist=args.apply))
    counts = {}
    for row in rows:
        status = row['status']
        counts[status] = counts.get(status, 0) + 1
        print(status.upper(), row.get('name', row['entity_id']), row.get('reason', ''))
        for candidate in row.get('candidates', [])[:3]:
            print('  Candidate (not an automatic selection):', candidate['label'])
    report = {'dry_run': not args.apply, 'counts': counts, 'results': rows,
              'attribution': 'OpenStreetMap contributors', 'policy': 'https://operations.osmfoundation.org/policies/nominatim/'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        args.report.chmod(0o600)
    print('Counts:', json.dumps(counts, sort_keys=True))
    print('Apply mode: see per-record persisted flags.' if args.apply else 'Dry run: no database writes; provider responses may be cached locally.')
    return 1 if any(row['status'] in {'store_failed', 'unavailable'} for row in rows) else 0


if __name__ == '__main__':
    raise SystemExit(main())
