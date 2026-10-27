#!/usr/bin/env python3
"""Find map coordinates for the saved restaurants and destinations that have none (the screenshots imported before the location step existed).

Dry run by default. Only an exact, unambiguous map match is ever written (with --apply); everything else is listed with the places the map proposed, so you can
confirm one in the app or pin it with set_entity_location.py. Never guesses."""
import argparse
from dataclasses import replace
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app import geocode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    real_env.load_env(args.env_file)
    with real_repository() as repo:
        loops = repo.get_active_open_loops(limit=1000)
        wanted = {k.entity_id for k in repo.get_loop_entities([l.loop_id for l in loops])}
        todo = [e for e in repo.get_entities(sorted(wanted)) if e.domain in ('food', 'travel') and e.entity_type in geocode.PLACE_TYPES and geocode.eligible(e)]
        print(f'{len(todo)} saved place(s) in active intentions without a verified location.\n')
        for entity in todo:
            found = geocode.resolve(entity)
            where = ', '.join(p for p in (entity.location_name, entity.city) if p)
            if found['status'] == 'resolved':
                print(f"RESOLVED   {entity.name} ({where}) -> {found['lat']:.5f}, {found['lon']:.5f}  {found['location_id']}\n           {found['display_name'][:110]}")
                if args.apply:
                    repo.save_entity(replace(entity, metadata=geocode.metadata_for(entity, found)))
                    print('           saved')
            else:
                print(f"UNRESOLVED {entity.name} ({where}): {found['reason']}")
                for c in found['candidates'][:3]:
                    print(f"           maybe: {c['label'][:100]}")
        if not args.apply:
            print('\nDry run: nothing written. Add --apply to save the RESOLVED ones.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
