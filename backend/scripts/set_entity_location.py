#!/usr/bin/env python3
"""Record a verified coordinate on one saved place so proximity checks (phone GPS, Context Simulator) can match it.

Recall never geocodes. A place only matches by distance when its entity metadata carries latitude, longitude, location_verified="true" and a
location_source. This script writes exactly those four fields, nothing else, and only with --apply. Without --apply it shows what it would do.

    set_entity_location.py --name "Elmo" --lat -37.7860 --lon 144.9800 --source "Google Maps pin, checked 2026-10-27"   # dry run
    ... --apply --entity-id ent_...                                                                                       # write

Use coordinates you checked yourself (a map pin on the real address). Do not guess. Shopping products also need --store-name (a physical store)."""
import argparse
from dataclasses import replace
from pathlib import Path

import real_env
from real_env import real_repository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', help='substring of the saved place name to search for')
    parser.add_argument('--entity-id')
    parser.add_argument('--lat', type=float)
    parser.add_argument('--lon', type=float)
    parser.add_argument('--source', help='where the coordinate came from, e.g. "Google Maps pin, checked <date>"')
    parser.add_argument('--store-name', help='required for shopping entities: the physical store')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    real_env.load_env(args.env_file)
    with real_repository() as repo:
        entities = repo.list_entities()
        found = [e for e in entities if (args.entity_id and e.entity_id == args.entity_id) or (args.name and args.name.lower() in e.name.lower())]
        if not found:
            print('No saved place matches. Names in the saved history:')
            for e in sorted(entities, key=lambda e: e.name):
                if e.domain in ('food', 'travel', 'shopping'):
                    print(f'  {e.entity_id}  {e.domain:9} {e.name}')
            return 1
        for e in found:
            located = (e.metadata or {}).get('location_verified', '').lower() == 'true'
            print(f'{e.entity_id}  {e.domain:9} {e.name}   verified coordinates: {"YES " + e.metadata.get("latitude", "") + "," + e.metadata.get("longitude", "") if located else "no"}')
        if args.lat is None or args.lon is None or not args.source:
            print('\nGive --lat, --lon and --source (and --entity-id when several match) to continue.')
            return 0
        if len(found) != 1:
            print('\nSeveral places match; pass --entity-id for exactly one.')
            return 1
        entity = found[0]
        if not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180):
            print('Coordinates out of range.')
            return 1
        if entity.domain == 'shopping' and not args.store_name:
            print('A shopping product only matches by location through a physical store. Pass --store-name.')
            return 1
        metadata = {**(entity.metadata or {}), 'latitude': f'{args.lat:.7f}', 'longitude': f'{args.lon:.7f}', 'location_verified': 'true', 'location_source': args.source}
        if args.store_name:
            metadata.update(location_role='store', store_name=args.store_name)
        print(f'\n{"WRITE" if args.apply else "DRY RUN"}: {entity.name} -> {args.lat:.7f}, {args.lon:.7f}  source="{args.source}"')
        if args.apply:
            repo.save_entity(replace(entity, metadata=metadata))
            print('Saved. Restart is not needed; the Context Simulator reads it on the next evaluation.')
        else:
            print('Nothing written. Add --apply to save.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
