"""The resettable demo workspace: an in-memory repository seeded from a snapshot of the canonical historical state.

It exists so a live, real-model demo can be recorded without writing to canonical, append-only Zetaris. Evidence and loops are the same records
(read from Zetaris once and committed as backend/demo/snapshot.json); the models and agents are the real ones. Nothing here is a fallback: it is
selected explicitly with RECALL_MODE=demo and every run it produces is labelled workspace 'demo'.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.repositories.memory import InMemoryLoopRepository

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'demo' / 'snapshot.json'


class SnapshotError(RuntimeError):
    pass


def export_snapshot(repository) -> dict:
    """Read-only. `repository` is a ZetarisRepository. Only active loops are kept; retired history is not part of the story."""
    evidence = repository.list_evidence()
    loops = repository.get_active_open_loops(limit=1000)
    links = repository.get_evidence_entities([e.evidence_id for e in evidence])
    loop_links = repository.get_loop_entities([l.loop_id for l in loops])
    entities = repository.list_entities()
    return {
        'meta': {'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': 'zetaris',
                 'counts': {'evidence': len(evidence), 'entities': len(entities), 'evidence_entities': len(links), 'active_loops': len(loops),
                            'loop_entities': len(loop_links)}},
        'evidence': [asdict(e) for e in evidence],
        'entities': [asdict(e) for e in entities],
        'evidence_entities': [asdict(k) for k in links],
        'loops': [{**asdict(l), 'status': l.status.value} for l in loops],
        'loop_entities': [asdict(k) for k in loop_links],
    }


def read_snapshot(path: Path = SNAPSHOT_PATH) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        raise SnapshotError(f'Demo snapshot is missing or unreadable: {path}. Create it with backend/scripts/export_snapshot.py.') from None
    counts = data.get('meta', {}).get('counts', {})
    if counts.get('evidence') != len(data.get('evidence', [])) or counts.get('active_loops') != len(data.get('loops', [])):
        raise SnapshotError('Demo snapshot counts do not match its contents.')
    return data


def seed(repository: InMemoryLoopRepository, data: dict) -> InMemoryLoopRepository:
    """Replace everything in `repository` (in place, so holders of the object keep working) with the snapshot."""
    repository.evidence.clear()
    repository.entities.clear()
    repository.evidence_entities.clear()
    repository.loops.clear()
    repository.loop_entities.clear()
    repository.check_ins.clear()
    entities = {e['entity_id']: Entity(**e) for e in data['entities']}
    links = [EvidenceEntity(**k) for k in data['evidence_entities']]
    for item in data['evidence']:
        evidence = Evidence(**item)
        mine = [k for k in links if k.evidence_id == evidence.evidence_id]
        repository.save_evidence(evidence, [entities[k.entity_id] for k in mine], mine)
    repository.entities.update(entities)
    for item in data['loops']:
        repository.save_open_loop(OpenLoop(**{**item, 'status': LoopStatus(item['status'])}))
    for link in data['loop_entities']:
        repository.link_loop_entity(LoopEntity(**link))
    return repository


def open_demo_repository(path: Path = SNAPSHOT_PATH) -> InMemoryLoopRepository:
    return seed(InMemoryLoopRepository(), read_snapshot(path))


def workspace_info(data: dict | None = None) -> dict:
    meta = (data or read_snapshot()).get('meta', {})
    return {'kind': 'demo workspace', 'storage': 'in-memory, resettable', 'seeded_from': meta.get('source'),
            'snapshot_exported_at': meta.get('exported_at'), 'snapshot_counts': meta.get('counts')}
