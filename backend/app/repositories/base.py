"""Repository contract the Open Loop Agent depends on.

Implementation-agnostic: Ica can back this with Zetaris; tests use the in-memory fake.
Retrieval semantics (what counts as "related") belong to the implementation; the agent
treats results as candidates and validates every id it is given.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop


class LoopRepository(Protocol):
    def save_evidence(self, evidence: Evidence, entities: Sequence[Entity],
                      links: Sequence[EvidenceEntity]) -> None:
        """Persist one evidence record with its entities and links as a unit.

        Entities are upserted by entity_id (the same real-world entity may appear in many
        screenshots). Evidence is append-only: it is never modified or deleted by agents.
        """

    def get_related_evidence(self, entity_ids: Sequence[str], *, domain: str | None = None,
                             exclude_evidence_ids: Sequence[str] = (), limit: int = 10) -> list[Evidence]: ...

    def get_related_entities(self, entity_ids: Sequence[str], *, domain: str | None = None,
                             limit: int = 20) -> list[Entity]: ...

    def get_candidate_open_loops(self, entity_ids: Sequence[str], *, domain: str | None = None,
                                 limit: int = 5) -> list[OpenLoop]: ...

    def get_active_open_loops(self, *, limit: int = 10) -> list[OpenLoop]:
        """Loops with status OPEN or ACTIVE, most recently updated first."""
        ...

    def get_open_loop(self, loop_id: str) -> OpenLoop | None: ...

    def get_entities(self, entity_ids: Sequence[str]) -> list[Entity]: ...

    def get_loop_entities(self, loop_ids: Sequence[str]) -> list[LoopEntity]: ...

    def save_open_loop(self, loop: OpenLoop) -> OpenLoop: ...

    def update_open_loop(self, loop_id: str, *, title: str | None = None, domain: str | None = None,
                         status: LoopStatus | None = None, confidence: float | None = None,
                         updated_at: str | None = None) -> OpenLoop: ...

    def link_loop_entity(self, link: LoopEntity) -> None: ...
