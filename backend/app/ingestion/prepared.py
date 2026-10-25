"""Transparent saved-perception conversion; never calls a model or edits input JSON."""
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path

from backend.app.agents.evidence import parse_evidence
from backend.app.ingestion.evidence_bridge import Ingested, ingest
from backend.app.repositories.memory import InMemoryLoopRepository


class PreparedDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedEvidence:
    graph: Ingested
    document: dict
    artifact_sha256: str


def load_prepared(path: Path, image_root: Path) -> PreparedEvidence:
    try:
        data = path.read_bytes()
        document = json.loads(data)
    except (OSError, ValueError):
        raise PreparedDataError('Cannot read the prepared Evidence JSON.') from None
    required = {'schema_version', 'evidence_id', 'source', 'image_ref', 'image_sha256', 'timestamp', 'extraction', 'raw_response', 'receipt'}
    if not isinstance(document, dict) or set(document) != required or document['schema_version'] != 1:
        raise PreparedDataError('Unsupported prepared Evidence envelope; original JSON was not changed.')
    for field in ('evidence_id', 'source', 'image_ref', 'image_sha256', 'timestamp', 'raw_response'):
        if not isinstance(document[field], str) or not document[field]:
            raise PreparedDataError('Prepared Evidence has missing or invalid metadata.')
    name = document['image_ref']
    if Path(name).name != name:
        raise PreparedDataError('Prepared image_ref must be the original neutral basename in the flat image folder.')
    root = image_root.resolve()
    image = (root / name).resolve()
    if image.parent != root or not image.is_file():
        raise PreparedDataError('Referenced screenshot is missing or outside the supplied image folder.')
    if hashlib.sha256(image.read_bytes()).hexdigest() != document['image_sha256']:
        raise PreparedDataError('Screenshot bytes no longer match the prepared Evidence artifact.')
    try:
        timestamp = datetime.fromisoformat(document['timestamp'])
        if timestamp.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise PreparedDataError('Prepared timestamp must include a timezone.') from None
    extraction = parse_evidence(document['raw_response'])
    # The existing parser performs its documented location cleanup. Preserve both
    # the exact returned text and its normalized structure; never silently alter either.
    if asdict(extraction) != document['extraction']:
        raise PreparedDataError('Prepared structure differs from parsing the preserved model response.')
    if not isinstance(document['receipt'], dict):
        raise PreparedDataError('Prepared receipt must be an object.')
    graph = ingest(extraction, InMemoryLoopRepository(), source=document['source'], image_ref=name,
                   captured_at=document['timestamp'], new_id=lambda: document['evidence_id'])
    return PreparedEvidence(graph, document, hashlib.sha256(data).hexdigest())
