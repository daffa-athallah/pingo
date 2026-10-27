#!/usr/bin/env python3
"""Choose cover photos for the saved items that have none. Dry run by default (it searches and lets the Cover Agent choose, but stores nothing).

Needs GOOGLE_CSE_KEY and GOOGLE_CSE_CX (Google Programmable Search, image search) and Nightshift in backend/.env.
    backfill_covers.py                     # dry run over every active single-subject intention
    backfill_covers.py --only "Elmo"       # one item
    backfill_covers.py --apply             # keep the chosen covers (writes a small piece of metadata to Zetaris and caches the image)
"""
import argparse
import asyncio
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app import covers
from backend.app.adapters.nightshift import ModelGateway
from backend.app.cover_service import ensure_cover


async def main(args) -> int:
    if not covers.provider_configured():
        print('Set GOOGLE_CSE_KEY and GOOGLE_CSE_CX in backend/.env first (Google Programmable Search, image search).')
        return 1
    with real_repository() as repo:
        loops = repo.get_active_open_loops(limit=1000)
        links = repo.get_loop_entities([l.loop_id for l in loops])
        async with ModelGateway.from_env() as gateway:
            for loop in loops:
                entities = repo.get_entities(sorted({k.entity_id for k in links if k.loop_id == loop.loop_id}))
                if len(entities) != 1 or entities[0].domain not in ('food', 'shopping', 'travel'):
                    continue
                if args.only and args.only.lower() not in loop.title.lower():
                    continue
                result = await ensure_cover(repo, entities[0], loop.title, gateway, apply=args.apply)
                print(f"{loop.title[:60]:60}  {result['status']:12} {result.get('reason') or result.get('page') or ''}"[:200])
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    arguments = parser.parse_args()
    real_env.load_env(arguments.env_file)
    raise SystemExit(asyncio.run(main(arguments)))
