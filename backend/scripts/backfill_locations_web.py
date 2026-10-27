#!/usr/bin/env python3
"""Run the Location Agent (web search -> street address -> verified on the map) for saved places that still have no coordinate.
Dry run by default; --apply stores the verified ones. Uses the real models (Nightshift) and writes only entity metadata."""
import argparse
import asyncio
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app import geocode
from backend.app.adapters.nightshift import ModelGateway
from backend.app.location_web import find_location
from dataclasses import replace


async def main(args) -> int:
    with real_repository() as repo:
        loops = repo.get_active_open_loops(limit=1000)
        wanted = {k.entity_id for k in repo.get_loop_entities([l.loop_id for l in loops])}
        todo = [e for e in repo.get_entities(sorted(wanted)) if e.domain in ('food', 'travel') and e.entity_type in geocode.PLACE_TYPES and not geocode.verified(e)]
        print(f'{len(todo)} saved place(s) without a verified location.\n')
        async with ModelGateway.from_env() as gateway:
            for entity in todo:
                if args.only and args.only.lower() not in entity.name.lower():
                    continue
                result = await find_location(entity, gateway)
                where = ', '.join(p for p in (entity.location_name, entity.city) if p)
                if result['status'] == 'resolved':
                    print(f"RESOLVED   {entity.name} ({where}) -> {result['lat']:.5f}, {result['lon']:.5f}  {result['address']}")
                    if args.apply:
                        repo.save_entity(replace(entity, metadata={**(entity.metadata or {}), **result['metadata'], 'location_lookup_status': 'resolved_web'}))
                        print('           saved')
                else:
                    print(f"{result['status'].upper():10} {entity.name} ({where}): {result['reason'][:140]}")
        if not args.apply:
            print('\nDry run: nothing written. Add --apply to save the RESOLVED ones.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--only', help='only places whose name contains this text')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    real_env.load_env(args.env_file)
    raise SystemExit(asyncio.run(main(args)))
