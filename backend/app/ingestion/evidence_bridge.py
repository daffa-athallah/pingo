"""Bridge: Evidence Agent extraction -> canonical domain records -> repository.

Mapping lives here so neither agent depends on storage shapes. No storage-specific logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Callable
import uuid

from backend.app.agents.evidence import Entity as ExtractedEntity, Evidence as Extraction, clean_location
from backend.app.domain import models as m
from backend.app.repositories.base import LoopRepository

_LINK_CONFIDENCE = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
RELATIONSHIP = 'depicted'


@dataclass(frozen=True)
class Ingested:
    evidence: m.Evidence
    entities: list[m.Entity]
    links: list[m.EvidenceEntity]


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().split())


def entity_id(domain: str, extracted: ExtractedEntity) -> str:
    """Deterministic MVP identity. type/category/subcategory/location_name are mutable
    descriptive metadata the vision model may label differently, so they are NOT identity.

    shopping: domain + brand + name.  food/travel (and any other domain): domain + name + city.
    """
    domain = _norm(domain)
    if domain == 'shopping':
        parts = [domain, _norm(extracted.brand), _norm(extracted.name)]
    else:
        parts = [domain, _norm(extracted.name), _norm(extracted.location.city if extracted.location else None)]
    return 'ent_' + hashlib.sha1('\x1f'.join(parts).encode()).hexdigest()[:12]


def ingest(extraction: Extraction, repository: LoopRepository, *, source: str = 'screenshot',
           image_ref: str | None = None, captured_at: str | None = None,
           new_id: Callable[[], str] | None = None) -> Ingested:
    evidence_id = (new_id or (lambda: 'ev_' + uuid.uuid4().hex[:12]))()
    timestamp = captured_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    evidence = m.Evidence(evidence_id, source, extraction.domain, extraction.summary, timestamp,
                          extraction.sensitive, extraction.confidence, image_ref)
    entities: dict[str, m.Entity] = {}
    for item in extraction.entities:
        item = clean_location(item)
        loc = item.location
        eid = entity_id(extraction.domain, item)
        entities.setdefault(eid, m.Entity(
            eid, item.type, extraction.domain, item.name, item.category, item.subcategory, item.brand,
            loc.location_name if loc else None, loc.city if loc else None, loc.country if loc else None,
            # Sensitive screenshots keep no free-form attributes; they may hold account or private values.
            {} if extraction.sensitive else dict(item.attributes)))
    links = [m.EvidenceEntity(evidence_id, eid, RELATIONSHIP, _LINK_CONFIDENCE[extraction.confidence]) for eid in entities]
    repository.save_evidence(evidence, list(entities.values()), links)
    return Ingested(evidence, list(entities.values()), links)
