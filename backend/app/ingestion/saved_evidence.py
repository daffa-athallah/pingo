"""Read the actual batch_evidence.py export without changing model-generated JSON.

That export has source_file/extraction/receipt, not an ID, timestamp or raw model
text. IDs are application-generated hashes of source basename, image bytes and
canonical extraction. The initial timestamp is JSON file mtime (export metadata,
NOT an inferred capture time). On replay the stored timestamp is authoritative.
The existing bridge alone maps extraction fields and determines entity identity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from backend.app.agents.evidence import EvidenceError, parse_evidence
from backend.app.ingestion.evidence_bridge import Ingested, ingest
from backend.app.repositories.memory import InMemoryLoopRepository


class SavedEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SavedEvidence:
    graph: Ingested
    filename: str
    artifact_sha256: str
    image_sha256: str
    receipt: dict


def read_saved_evidence(path: Path, image_root: Path, *, model: str = 'gpt-4o-mini') -> SavedEvidence:
    try:
        content = path.read_bytes()
        document = json.loads(content)
    except (OSError, ValueError):
        raise SavedEvidenceError('Cannot read saved Evidence JSON.') from None
    if not isinstance(document, dict) or set(document) != {'source_file', 'extraction', 'receipt'}:
        raise SavedEvidenceError('Unsupported export schema; original JSON was preserved.')
    name = document['source_file']
    if not isinstance(name, str) or not name or Path(name).name != name or name in {'.', '..'}:
        raise SavedEvidenceError('source_file must be a basename in the unsorted screenshot folder.')
    root = image_root.resolve()
    image = (root / name).resolve()
    if image.parent != root or not image.is_file():
        raise SavedEvidenceError('The referenced screenshot is missing or outside the image folder.')
    try:
        extraction = parse_evidence(json.dumps(document['extraction']))
    except (EvidenceError, ValueError, TypeError):
        raise SavedEvidenceError('Extraction does not match the current Evidence Agent contract.') from None
    if asdict(extraction) != document['extraction']:
        raise SavedEvidenceError('Extraction would require normalization; inspect explicitly rather than rewrite it silently.')
    receipt = document['receipt']
    if not isinstance(receipt, dict) or set(receipt) != {'requested_model', 'routed_model', 'provider'}:
        raise SavedEvidenceError('Export has no canonical routing receipt.')
    if receipt['provider'] != 'openai' or receipt['requested_model'] != model or receipt['routed_model'] != model:
        raise SavedEvidenceError('Perception receipt does not match the expected model/provider.')
    image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    identity = json.dumps({'source_file': name, 'image_sha256': image_sha256, 'extraction': document['extraction']},
                          sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    evidence_id = 'ev_' + hashlib.sha256(identity.encode()).hexdigest()[:24]
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='microseconds')
    graph = ingest(extraction, InMemoryLoopRepository(), source='screenshot', image_ref=name,
                   captured_at=timestamp, new_id=lambda: evidence_id)
    return SavedEvidence(graph, path.name, hashlib.sha256(content).hexdigest(), image_sha256, dict(receipt))


def stored_graph(repository, artifact: SavedEvidence) -> tuple[Ingested, bool]:
    """Reuse the immutable stored timestamp after copying/reformatting an export.

    Every other Evidence field and all historical edges still go through the
    repository's conflict checks. Descriptive entity metadata may evolve normally.
    """
    graph = artifact.graph
    previous = repository.get_evidence(graph.evidence.evidence_id)
    if previous is not None:
        graph = replace(graph, evidence=replace(graph.evidence, timestamp=previous.timestamp))
    return graph, previous is not None


def verify_stored_graph(repository, graph: Ingested, *, exact_entities: bool = False) -> None:
    if repository.get_evidence(graph.evidence.evidence_id) != graph.evidence:
        raise SavedEvidenceError('Evidence readback failed.')
    ids = [entity.entity_id for entity in graph.entities]
    entities = repository.get_entities(ids)
    if {entity.entity_id for entity in entities} != set(ids):
        raise SavedEvidenceError('Entity IDs did not round-trip unchanged.')
    if exact_entities and entities != graph.entities:
        raise SavedEvidenceError('New entity fields did not round-trip unchanged.')
    actual = repository.get_evidence_entities([graph.evidence.evidence_id])
    if len(actual) != len(set(graph.links)) or set(actual) != set(graph.links):
        raise SavedEvidenceError('Persisted evidence/entity edges differ or contain duplicates.')
    for entity_id in ids:
        if graph.evidence not in repository.get_related_evidence([entity_id], limit=10000):
            raise SavedEvidenceError('Stored entity does not ground back to the original Evidence.')
