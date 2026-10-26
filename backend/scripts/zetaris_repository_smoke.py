#!/usr/bin/env python3
"""Phase 1: prove the ZetarisRepository abstraction reads the real imported dataset. Read-only, no model calls."""
import argparse
from dataclasses import is_dataclass
from pathlib import Path

import real_env
from real_env import real_repository
from backend.app.adapters.zetaris import ZetarisError
from backend.app.domain.models import Entity, Evidence, EvidenceEntity


def check(ok: bool, label: str) -> None:
    print(('[PASS] ' if ok else '[FAIL] ') + label)
    if not ok:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--probe', default='omb burger', help='case-insensitive name fragment of the entity to retrieve')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        with real_repository() as repo:
            evidence = repo.list_evidence()
            entities = repo.list_entities()
            links = repo.get_evidence_entities([e.evidence_id for e in evidence])
            print(f'[INFO] evidence={len(evidence)} entities={len(entities)} evidence_entity_links={len(links)}')
            check(bool(evidence) and all(isinstance(e, Evidence) for e in evidence), 'Evidence returned as canonical Evidence dataclasses')
            check(bool(entities) and all(isinstance(e, Entity) and isinstance(e.metadata, dict) for e in entities), 'Entities returned as canonical Entity dataclasses (metadata decoded)')
            check(bool(links) and all(isinstance(k, EvidenceEntity) for k in links), 'Links returned as canonical EvidenceEntity dataclasses')
            check(not any(isinstance(x, (tuple, list, dict)) for x in (*evidence, *entities, *links)) and is_dataclass(evidence[0]), 'no raw JDBC rows leak out of the repository')
            check({k.entity_id for k in links} <= {e.entity_id for e in entities}, 'every link resolves to a stored entity')
            probe = [e for e in entities if args.probe.lower() in e.name.lower()]
            check(len(probe) == 1, f'"{args.probe}" retrieved through the repository ({probe[0].name if probe else "none"})')
            target = probe[0]
            check(repo.get_entities([target.entity_id]) == [target], 'get_entities round-trips the entity')
            related = repo.get_related_evidence([target.entity_id])
            check(bool(related), f'get_related_evidence -> {len(related)} Evidence record(s): {[e.evidence_id for e in related]}')
            check(all(any(k.evidence_id == e.evidence_id and k.entity_id == target.entity_id for k in links) for e in related), 'related Evidence is backed by persisted links')
            others = repo.get_related_entities([target.entity_id])
            check(all(o.entity_id != target.entity_id for o in others), f'get_related_entities -> {len(others)} co-occurring entities (probe excluded): {[o.name for o in others]}')
            print(f'[INFO] active open loops currently stored: {len(repo.get_active_open_loops(limit=1000))}')
            domains = {}
            for e in evidence:
                domains[e.domain] = domains.get(e.domain, 0) + 1
            print('[INFO] evidence by domain:', dict(sorted(domains.items())))
            print('[INFO] sensitive evidence:', sum(e.sensitive for e in evidence))
        print('[PASS] repository smoke complete')
        return 0
    except ZetarisError as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
