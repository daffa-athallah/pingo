"""Storage-agnostic records shared by agents and data layers (Zetaris, in-memory fakes)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LoopStatus(str, Enum):
    OPEN = 'OPEN'
    ACTIVE = 'ACTIVE'
    DORMANT = 'DORMANT'
    RESOLVED = 'RESOLVED'
    INVALIDATED = 'INVALIDATED'


class ContextType(str, Enum):
    CALENDAR = 'CALENDAR'
    LOCATION = 'LOCATION'
    TIME = 'TIME'
    REAL_WORLD_EVENT = 'REAL_WORLD_EVENT'  # reserved: no retrieval is implemented yet


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source: str
    domain: str
    summary: str
    timestamp: str
    sensitive: bool
    confidence: str
    image_ref: str | None = None


@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    domain: str
    name: str
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    location_name: str | None = None
    city: str | None = None
    country: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceEntity:
    evidence_id: str
    entity_id: str
    relationship: str
    confidence: float


@dataclass(frozen=True)
class OpenLoop:
    loop_id: str
    title: str
    domain: str
    status: LoopStatus
    confidence: float
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LoopEntity:
    loop_id: str
    entity_id: str
    relationship: str
    confidence: float


@dataclass(frozen=True)
class ContextEvent:
    """Something happening now or soon: a calendar entry, a place the user is at, or the time of day."""
    context_id: str
    context_type: ContextType
    title: str
    occurs_at: str | None = None
    location_name: str | None = None
    city: str | None = None
    country: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
