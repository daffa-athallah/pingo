"""In-memory LoopRepository for offline tests and local development."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from backend.app.domain.models import CheckIn, Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop


class InMemoryLoopRepository:
    def __init__(self):
        self.evidence: dict[str, Evidence] = {}
        self.entities: dict[str, Entity] = {}
        self.evidence_entities: list[EvidenceEntity] = []
        self.loops: dict[str, OpenLoop] = {}
        self.loop_entities: list[LoopEntity] = []
        self.check_ins: dict[str, CheckIn] = {}
        self.context_events = {}
        self.context_evaluations = {}
        self.notifications = {}

    def save_entity(self, entity: Entity) -> None:
        """Same metadata-upsert helper as Zetaris (also present on current main)."""
        self.entities[entity.entity_id] = entity

    def save_evidence(self, evidence: Evidence, entities: Sequence[Entity], links: Sequence[EvidenceEntity]) -> None:
        self.evidence[evidence.evidence_id] = evidence
        self.entities.update({entity.entity_id: entity for entity in entities})
        self.evidence_entities.extend(l for l in links if l not in self.evidence_entities)

    def _evidence_ids_for(self, entity_ids: Sequence[str]) -> list[str]:
        wanted = set(entity_ids)
        return [link.evidence_id for link in self.evidence_entities if link.entity_id in wanted]

    def get_related_evidence(self, entity_ids, *, domain=None, exclude_evidence_ids=(), limit=10):
        seen = []
        for evidence_id in self._evidence_ids_for(entity_ids):
            item = self.evidence.get(evidence_id)
            if item and evidence_id not in exclude_evidence_ids and (domain is None or item.domain == domain) \
                    and item not in seen:
                seen.append(item)
        return sorted(seen, key=lambda e: e.timestamp, reverse=True)[:limit]

    def get_related_entities(self, entity_ids, *, domain=None, limit=20):
        related = {eid for ev_id in self._evidence_ids_for(entity_ids)
                   for eid in (l.entity_id for l in self.evidence_entities if l.evidence_id == ev_id)}
        return [self.entities[eid] for eid in sorted(related)
                if eid in self.entities and eid not in entity_ids
                and (domain is None or self.entities[eid].domain == domain)][:limit]

    def get_candidate_open_loops(self, entity_ids, *, domain=None, limit=5):
        wanted = set(entity_ids)
        loop_ids = {l.loop_id for l in self.loop_entities if l.entity_id in wanted}
        loops = [loop for loop in self.loops.values()
                 if loop.status not in (LoopStatus.INVALIDATED,) and
                 (loop.loop_id in loop_ids or (domain is not None and loop.domain == domain))]
        return sorted(loops, key=lambda l: l.updated_at, reverse=True)[:limit]

    def get_active_open_loops(self, *, limit=10):
        loops = [l for l in self.loops.values() if l.status in (LoopStatus.OPEN, LoopStatus.ACTIVE)]
        return sorted(loops, key=lambda l: l.updated_at, reverse=True)[:limit]

    def get_open_loop(self, loop_id):
        return self.loops.get(loop_id)

    def get_entities(self, entity_ids):
        return [self.entities[e] for e in entity_ids if e in self.entities]

    def get_loop_entities(self, loop_ids):
        return [l for l in self.loop_entities if l.loop_id in set(loop_ids)]

    def save_open_loop(self, loop):
        self.loops[loop.loop_id] = loop
        return loop

    def update_open_loop(self, loop_id, *, title=None, domain=None, status=None, confidence=None, updated_at=None):
        current = self.loops[loop_id]
        changes = {k: v for k, v in dict(title=title, domain=domain, status=status,
                                         confidence=confidence, updated_at=updated_at).items() if v is not None}
        self.loops[loop_id] = replace(current, **changes)
        return self.loops[loop_id]

    def link_loop_entity(self, link):
        if not any((l.loop_id, l.entity_id, l.relationship) == (link.loop_id, link.entity_id, link.relationship)
                   for l in self.loop_entities):
            self.loop_entities.append(link)

    # Read helpers that ZetarisRepository also offers, so the API can treat both the same way. They add no agent behaviour.
    def get_evidence(self, evidence_id: str):
        return self.evidence.get(evidence_id)

    def list_evidence(self) -> list[Evidence]:
        return sorted(self.evidence.values(), key=lambda e: (e.timestamp, e.evidence_id))

    def list_entities(self, *, domain: str | None = None) -> list[Entity]:
        return sorted((e for e in self.entities.values() if domain is None or e.domain == domain), key=lambda e: e.entity_id)

    def get_evidence_entities(self, evidence_ids: Sequence[str]) -> list[EvidenceEntity]:
        wanted = set(evidence_ids)
        return sorted((k for k in self.evidence_entities if k.evidence_id in wanted), key=lambda k: (k.evidence_id, k.entity_id, k.relationship))

    def save_check_in(self, check_in: CheckIn) -> None:
        self.check_ins[check_in.check_in_id] = check_in

    def save_context_event(self, event):
        self.context_events[event.context_id] = event

    def get_context_events(self):
        return list(self.context_events.values())

    def save_context_evaluation(self, evaluation):
        self.context_evaluations[evaluation.evaluation_id] = evaluation

    def get_context_evaluation(self, evaluation_id):
        return self.context_evaluations.get(evaluation_id)

    def save_notification(self, notification):
        self.notifications[notification.notification_id] = notification

    def get_notification(self, notification_id):
        return self.notifications.get(notification_id)

    def list_notifications(self):
        return sorted(self.notifications.values(), key=lambda n: n.created_at, reverse=True)

    def get_check_in(self, check_in_id: str) -> CheckIn | None:
        return self.check_ins.get(check_in_id)

    def get_check_ins(self, *, day=None, status=None) -> list[CheckIn]:
        return sorted((c for c in self.check_ins.values() if (day is None or c.day == day) and (status is None or c.status == status)),
                      key=lambda c: (c.created_at, c.check_in_id))
