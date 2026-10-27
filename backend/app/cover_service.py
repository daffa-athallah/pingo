"""Give a saved item a cover photo: search, let the Cover Agent choose among what was found, keep the chosen image, record where it came from."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Awaitable, Callable

from backend.app import covers
from backend.app.agents.cover import CoverAgent, CoverError


async def ensure_cover(repository, entity, description: str, gateway, *, emit: Callable[..., object] | None = None, apply: bool = True,
                       search=None, fetch=covers.fetch) -> dict:
    """{'status': 'has'|'no_provider'|'no_candidates'|'refused'|'chosen'|'failed', ...}. Never raises: a missing cover is not an error."""
    say = emit or (lambda *a, **k: None)
    if covers.has_cover(entity):
        return {'status': 'has'}
    search = search or (covers.search_google if covers.provider_configured() else None)
    if search is None:
        return {'status': 'no_provider'}
    query = covers.subject_query(entity)
    try:
        found = await asyncio.to_thread(search, query)
        images, kept = [], []
        for candidate in found[:4]:
            raw = await asyncio.to_thread(fetch, candidate.thumb_url or candidate.image_url)
            small = covers.normalise(raw, 640) if raw else None
            if small:
                images.append(small)
                kept.append(candidate)
        if not images:
            say('COVER', 'NONE', f'No usable photos found for "{query}".')
            return {'status': 'no_candidates', 'query': query}
        say('COVER', 'SEARCHED', f'Found {len(images)} candidate photos for "{query}". The Cover Agent is choosing.', detail={'query': query, 'sources': [c.page_url for c in kept]})
        choice = await CoverAgent(gateway).choose(query, description, images)
        if choice.index is None:
            say('COVER', 'REFUSED', f'No candidate clearly shows it, so no cover: {choice.reason}')
            return {'status': 'refused', 'reason': choice.reason, 'query': query}
        chosen = kept[choice.index]
        full = await asyncio.to_thread(fetch, chosen.image_url)
        data = (covers.normalise(full, 900) if full else None) or images[choice.index]
        if not apply:
            return {'status': 'chosen', 'reason': choice.reason, 'page': chosen.page_url, 'query': query, 'applied': False}
        name = covers.store(data)
        repository.save_entity(replace(entity, metadata=covers.metadata_for(entity, file=name, candidate=chosen, alt=f'{entity.name}: {chosen.title}', reason=choice.reason)))
        say('COVER', 'CHOSEN', f'Cover chosen: {choice.reason}', detail={'source': chosen.page_url, 'file': name})
        return {'status': 'chosen', 'reason': choice.reason, 'page': chosen.page_url, 'query': query, 'applied': True}
    except (CoverError, Exception) as exc:  # noqa: BLE001 - a cover is optional; never break the run
        say('COVER', 'NONE', f'Cover search did not finish safely ({type(exc).__name__}).')
        return {'status': 'failed', 'error': type(exc).__name__}
