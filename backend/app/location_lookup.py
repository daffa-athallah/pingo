"""Location search tool after perception/persistence; no agent reasoning or Evidence rewriting.

The current upload boundary calls this once after a saved screenshot. Existing data can
use the same operation explicitly. Provider replies are never described as model output.
"""
import asyncio
import base64
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json

from backend.app import geocode

def _pack(candidates) -> str:
    """Zetaris strips the backslash from \\" inside a stored value, which corrupts the entity row; base64 has no characters that need escaping."""
    return 'b64:' + base64.b64encode(json.dumps(candidates, ensure_ascii=False).encode()).decode()


def _unpack(text: str):
    return json.loads(base64.b64decode(text[4:]).decode()) if text.startswith('b64:') else json.loads(text)



def utcnow():
    return datetime.now(timezone.utc)


def signature(entity):
    fields = [entity.name, entity.location_name, entity.city, entity.country, entity.metadata.get('address')]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()


def retry_due(entity, now):
    meta = entity.metadata
    if meta.get('location_lookup_status') not in {'ambiguous', 'not_found', 'unavailable'}:
        return True
    if meta.get('location_lookup_signature') != signature(entity):
        return True
    try:
        retry = datetime.fromisoformat(meta.get('location_lookup_retry_at', ''))
        return retry.tzinfo is None or retry <= now
    except ValueError:
        return True


def _result(entity, status, reason=None, candidates=None):
    return {'entity_id': entity.entity_id, 'name': entity.name, 'status': status, 'reason': reason,
            'candidates': candidates or [], 'latitude': entity.metadata.get('latitude') if geocode.verified(entity) else None,
            'longitude': entity.metadata.get('longitude') if geocode.verified(entity) else None,
            'location_id': entity.metadata.get('location_id') if geocode.verified(entity) else None}


async def enrich_entities(repository, entities, *, emit=None, resolver=None, clock=utcnow, force=False, persist=True):
    """Sequential, bounded enrichment. persist=False explicitly reports a dry run.

    force bypasses entity retry timestamps, not the provider cache or rate limit.
    One writer per application remains required (same limitation as the repository).
    """
    if not geocode.enabled():
        return []
    resolver = resolver or geocode.resolve
    entities = list({entity.entity_id: entity for entity in entities}.values())
    rows = []
    all_evidence = {e.evidence_id: e for e in repository.list_evidence()}
    links = repository.get_evidence_entities(list(all_evidence))
    def report(entity, status, reason, candidates=None):
        row = _result(entity, status, reason, candidates)
        rows.append(row)
        if emit:
            try:
                emit('LOCATION', status.upper(), reason, input_refs=[f'entity:{entity.entity_id}'],
                     next_step='STOP', detail={'source': 'OpenStreetMap contributors / Nominatim', **row})
            except Exception:
                pass  # observation never changes persistence or the upload outcome

    for entity in entities[:20]:
        evidence = [all_evidence[link.evidence_id] for link in links if link.entity_id == entity.entity_id and link.evidence_id in all_evidence]
        if not evidence or any(item.sensitive for item in evidence):
            # Do not send a sensitive entity name/address to an external provider or trace.
            rows.append({'entity_id': entity.entity_id, 'status': 'skipped_private_or_ungrounded'})
            continue
        if geocode.verified(entity):
            report(entity, 'located', 'The saved location already has verified coordinates; no search was sent.')
            continue
        if not geocode.eligible(entity):
            report(entity, 'skipped', 'This is not a physical restaurant, destination or store; product inventory/branches are not inferred.')
            continue
        if not force and not retry_due(entity, clock()):
            try:
                candidates = _unpack(entity.metadata.get('location_lookup_candidates', '[]'))
                candidates = candidates if isinstance(candidates, list) else []
            except ValueError:
                candidates = []
            report(entity, entity.metadata.get('location_lookup_status', 'deferred'), 'A recent lookup is retained; no search was repeated.',
                   candidates)
            continue
        try:
            found = await asyncio.to_thread(resolver, entity)
        except Exception:
            found = {'status': 'unavailable', 'reason': 'Location search failed safely; the place remains unlocated.', 'candidates': []}
        now = clock()
        try:
            with getattr(repository, 'unit_of_work', nullcontext)():
                latest = repository.get_entities([entity.entity_id])
                if not latest:
                    report(entity, 'stale', 'The entity is no longer available; no location was saved.')
                    continue
                current = latest[0]
                if geocode.verified(current):
                    report(current, 'located', 'A verified location was supplied during lookup; it was preserved.')
                    continue
                if signature(current) != signature(entity):
                    report(current, 'stale', 'Saved place details changed during lookup; no stale result was applied.')
                    continue
                status = found.get('status', 'unavailable')
                candidates = found.get('candidates', [])[:5]
                metadata = {**current.metadata, 'location_lookup_status': status, 'location_lookup_at': now.isoformat(),
                            'location_lookup_signature': signature(current),
                            'location_lookup_retry_at': (now + timedelta(seconds=300 if status == 'unavailable' else 86400)).isoformat(),
                            'location_lookup_reason': str(found.get('reason', 'Matched a unique map result.'))[:500].replace('"', "'"),
                            'location_lookup_candidates': _pack(candidates)}
                if status == 'resolved':
                    metadata = geocode.metadata_for(replace(current, metadata=metadata), found)
                else:
                    metadata['location_verified'] = 'false'
                updated = replace(current, metadata=metadata)
                if persist:
                    repository.save_entity(updated)
            report(updated, status, ('Resolved from a unique map result with matching saved locality.' if persist else 'Dry run: unique map result, no metadata written.') if status == 'resolved'
                   else metadata['location_lookup_reason'], candidates)
            rows[-1]['persisted'] = persist
        except Exception:
            report(entity, 'store_failed', 'Location metadata could not be saved; screenshot Evidence remains unchanged.')
    for entity in entities[20:]:
        rows.append({'entity_id': entity.entity_id, 'status': 'deferred', 'reason': 'Per-run lookup bound reached; use an explicit backfill for the remaining entities.'})
    return rows


async def enrich_evidence(repository, evidence_id, **kwargs):
    if not geocode.enabled():
        return []
    evidence = repository.get_evidence(evidence_id)
    if evidence is None or evidence.sensitive:
        return []
    ids = sorted({link.entity_id for link in repository.get_evidence_entities([evidence_id])})
    return await enrich_entities(repository, repository.get_entities(ids), **kwargs)
