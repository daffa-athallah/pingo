#!/usr/bin/env python3
"""Storage-only import of existing batch_evidence.py JSON; zero model calls.

plan validates everything without connecting. first proves one real Evidence
graph. batch requires that matching persisted storage proof. Neither command
creates or revises an Open Loop, or claims a complete orchestrator integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend.app.adapters.zetaris import ZetarisError
from backend.app.bootstrap import open_repository, sample_mode
from backend.app.ingestion.saved_evidence import SavedEvidenceError, read_saved_evidence, stored_graph, verify_stored_graph


def write_report(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(data, file, indent=2)
        file.write('\n')


def provenance(artifact, graph):
    return {'json_file': artifact.filename, 'artifact_sha256': artifact.artifact_sha256,
            'image_ref': graph.evidence.image_ref, 'image_sha256': artifact.image_sha256,
            'evidence_id': graph.evidence.evidence_id, 'timestamp': graph.evidence.timestamp,
            'entity_ids': [entity.entity_id for entity in graph.entities], 'perception_receipt': artifact.receipt}


def import_one(repository, artifact):
    graph, exists = stored_graph(repository, artifact)
    previous_entities = {entity.entity_id: entity for entity in repository.get_entities([entity.entity_id for entity in graph.entities])}
    repository.save_evidence(graph.evidence, graph.entities, graph.links)
    verify_stored_graph(repository, graph, exact_entities=not exists)
    return graph, {'inserted': int(not exists), 'skipped': int(exists), 'failed': 0,
                   'inserted_entities': sum(entity.entity_id not in previous_entities for entity in graph.entities) if not exists else 0,
                   'updated_entities': sum(entity.entity_id in previous_entities and previous_entities[entity.entity_id] != entity for entity in graph.entities) if not exists else 0}


def check_storage_proof(path, artifacts, repository):
    try:
        proof = json.loads(path.read_text())
        if proof.get('kind') != 'real_evidence_storage_roundtrip' or proof.get('verified') is not True:
            raise ValueError()
        item = next(item for item in artifacts if item.filename == proof['record']['json_file'])
        if item.artifact_sha256 != proof['record']['artifact_sha256'] or item.graph.evidence.evidence_id != proof['record']['evidence_id']:
            raise ValueError()
        graph, exists = stored_graph(repository, item)
        if not exists:
            raise ValueError()
        verify_stored_graph(repository, graph)
        return item
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        raise SavedEvidenceError('A matching, persisted first-record storage proof is required before batch import.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--input', type=Path, default=ROOT / 'sample_data/evidence')
    parser.add_argument('--images', type=Path, default=ROOT / 'screenshot')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('plan')
    first = commands.add_parser('first')
    first.add_argument('--file', required=True, help='Original JSON basename inside --input')
    first.add_argument('--proof', type=Path, required=True)
    batch = commands.add_parser('batch')
    batch.add_argument('--proof', type=Path, required=True)
    batch.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if any(not path.is_file() for path in args.env_file):
        parser.error('Explicit environment file is missing.')
    for path in [*args.env_file, ROOT / 'backend/.env.local']:
        if path.is_file():
            load_dotenv(path, override=False)
    try:
        files = sorted(args.input.glob('*.json'))
        if not files:
            raise SavedEvidenceError('No saved Evidence JSON found.')
        model = os.environ.get('METERLESS_VISION_MODEL', '').strip() or 'gpt-4o-mini'
        artifacts, errors = [], []
        for file in files:
            try:
                artifacts.append(read_saved_evidence(file, args.images, model=model))
            except SavedEvidenceError:
                errors.append(file.name)
        if errors:
            print(json.dumps({'validated': len(artifacts), 'failed': len(errors), 'files': errors, 'writes': 0, 'model_calls': 0}))
            raise SavedEvidenceError('All inputs must validate before any database write.')
        ids = [item.graph.evidence.evidence_id for item in artifacts]
        if len(ids) != len(set(ids)):
            raise SavedEvidenceError('Duplicate Evidence identities in the input batch; no writes made.')
        if args.command == 'plan':
            print(json.dumps({'validated': len(artifacts), 'entity_occurrences': sum(len(item.graph.entities) for item in artifacts),
                              'unique_entities': len({entity.entity_id for item in artifacts for entity in item.graph.entities}),
                              'writes': 0, 'model_calls': 0, 'timestamp_mapping': 'export JSON mtime initially; immutable stored timestamp on replay'}))
            return 0
        if sample_mode():
            raise SavedEvidenceError('Real import requires SAMPLE_MODE=false; no sample fallback is allowed.')
        with open_repository() as repository:
            if args.command == 'first':
                chosen = next((item for item in artifacts if item.filename == args.file), None)
                if chosen is None:
                    raise SavedEvidenceError('Requested first JSON is not in the validated input set.')
                if args.proof.exists():
                    proven = check_storage_proof(args.proof, artifacts, repository)
                    if proven.graph.evidence.evidence_id != chosen.graph.evidence.evidence_id:
                        raise SavedEvidenceError('Existing proof belongs to a different first record; no writes made.')
                    print('[SKIP] Existing real storage proof verified; no database writes or model calls.')
                    return 0
                graph, counts = import_one(repository, chosen)
                proof = {'kind': 'real_evidence_storage_roundtrip', 'verified': True,
                         'open_loop_verified': False, 'orchestrator_verified': False,
                         'record': provenance(chosen, graph), 'counts': counts, 'model_calls': 0}
                write_report(args.proof, proof)
                print('[PASS] Real Evidence, Entity IDs, exact fields and persisted graph edges verified.')
                print(json.dumps(counts))
                return 0
            if args.report.exists():
                raise SavedEvidenceError('Report already exists; choose a new report filename rather than overwrite it.')
            check_storage_proof(args.proof, artifacts, repository)
            counts = dict(inserted=0, skipped=0, failed=0, inserted_entities=0, updated_entities=0)
            records = []
            for index, artifact in enumerate(artifacts, 1):
                try:
                    graph, result = import_one(repository, artifact)
                    for key in counts:
                        counts[key] += result[key]
                    records.append(provenance(artifact, graph))
                    print(f'[{index}/{len(artifacts)}] {artifact.filename}: ' + ('skipped existing' if result['skipped'] else 'stored and verified'), flush=True)
                except Exception:
                    counts['failed'] += 1
                    write_report(args.report, {'kind': 'saved_evidence_import', 'verified': False, 'counts': counts, 'records': records, 'model_calls': 0})
                    raise SavedEvidenceError('Import stopped at a storage failure; completed records and failure report were preserved.') from None
            # Re-read the full batch after all entity upserts, without expecting
            # historical descriptive entity metadata to overwrite newer metadata.
            for artifact in artifacts:
                graph, exists = stored_graph(repository, artifact)
                if not exists:
                    raise SavedEvidenceError('A batch Evidence record disappeared during final verification.')
                verify_stored_graph(repository, graph)
                if hashlib.sha256((args.input / artifact.filename).read_bytes()).hexdigest() != artifact.artifact_sha256:
                    raise SavedEvidenceError('A source JSON changed during import; stored records were retained for review.')
            write_report(args.report, {'kind': 'saved_evidence_import', 'verified': True, 'counts': counts,
                                       'records': records, 'model_calls': 0, 'source_json_unchanged': True})
            print('[PASS] All stored Evidence graphs re-read and verified.')
            print(json.dumps(counts))
            return 0
    except (SavedEvidenceError, ZetarisError) as error:
        print('[BLOCKED]', str(error))
        return 1
    except Exception as error:
        print('[BLOCKED]', type(error).__name__ + '; raw content and credentials withheld.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
