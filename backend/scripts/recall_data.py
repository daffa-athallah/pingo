#!/usr/bin/env python3
"""Incremental real-data workflow: extract -> roundtrip -> batch -> run.

All original model responses are retained in private local artifacts. No filename
classification, raw reasoning, model fallback, secret logging or object creation.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.adapters.zetaris import ZetarisError
from backend.app.agents.evidence import EvidenceAgent, EvidenceError
from backend.app.bootstrap import build_orchestrator, open_repository, sample_mode
from backend.app.domain.models import ContextEvent, ContextType
from backend.app.ingestion.prepared import PreparedDataError, load_prepared


def write_private(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(document, output, indent=2, ensure_ascii=False)
        output.write('\n')
    path.chmod(0o600)


def receipt(gateway, model, provider):
    data = dict(gateway.last_routing)
    if data.get('requested_model') != model or data.get('routed_model') != model or data.get('provider') != provider:
        raise ModelGatewayError('Nightshift receipt does not match the configured model/provider; proof was not recorded.')
    return {key: data[key] for key in ('requested_model', 'routed_model', 'provider')}


def verified_proof(path, repository):
    try:
        proof = json.loads(path.read_text())
        if proof.get('kind') != 'real_zetaris_roundtrip' or not proof.get('verified'):
            raise ValueError()
        for label, provider in (('perception', 'open_loop'), ('reasoning', 'nvidia')):
            data = proof['receipts'][label]
            expected = 'openai' if label == 'perception' else provider
            if data['provider'] != expected or data['requested_model'] != data['routed_model']:
                raise ValueError()
        evidence = repository.get_evidence(proof['evidence_id'])
        loop = repository.get_open_loop(proof['loop_id'])
        edges = repository.get_loop_entities([proof['loop_id']])
        entity_ids = {edge.entity_id for edge in edges}
        grounded = repository.get_related_evidence(sorted(entity_ids), limit=10000)
        if evidence is None or loop is None or evidence not in grounded or set(proof['loop_entity_ids']) != entity_ids:
            raise ValueError()
        if {item.entity_id for item in repository.get_entities(proof['entity_ids'])} != set(proof['entity_ids']):
            raise ValueError()
        return proof
    except (OSError, ValueError, KeyError, TypeError):
        raise PreparedDataError('A valid real-data round-trip proof and matching persisted graph are required before continuing.') from None


async def extract(args):
    if args.output.exists():
        existing = load_prepared(args.output, args.image.parent)
        if existing.document['image_ref'] != args.image.name:
            raise PreparedDataError('Existing output belongs to a different screenshot; no model was called or file overwritten.')
        print('[SKIP] Valid prepared Evidence already exists; no model was called.')
        return
    async with ModelGateway.from_env() as gateway:
        class RecordingGateway:
            raw_response = None

            def __getattr__(self, key):
                return getattr(gateway, key)

            async def complete(self, *values, **keywords):
                self.raw_response = await gateway.complete(*values, **keywords)
                return self.raw_response

        recording = RecordingGateway()
        try:
            extraction = await EvidenceAgent(recording).observe(args.image)
        except EvidenceError:
            if recording.raw_response is not None:
                invalid = args.output.with_name(args.output.stem + '.invalid.' + uuid.uuid4().hex[:8] + '.json')
                write_private(invalid, {'kind': 'invalid_model_response', 'raw_response': recording.raw_response,
                                        'receipt': {key: gateway.last_routing.get(key) for key in ('requested_model', 'routed_model', 'provider')}})
            raise
        routing = receipt(gateway, gateway.vision_model, 'openai')
        document = {'schema_version': 1, 'evidence_id': 'ev_' + uuid.uuid4().hex[:12], 'source': 'screenshot',
                    'image_ref': args.image.name, 'image_sha256': hashlib.sha256(args.image.read_bytes()).hexdigest(),
                    'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'extraction': asdict(extraction), 'raw_response': recording.raw_response, 'receipt': routing}
        write_private(args.output, document)
        print('[PASS] Existing Evidence Agent completed once; exact returned text, normalized extraction and receipt saved privately.')
        print('[RECEIPT]', json.dumps(routing))


async def roundtrip(args):
    prepared = load_prepared(args.input, args.images)
    graph = prepared.graph
    with open_repository() as repository:
        if args.output.exists():
            verified_proof(args.output, repository)
            print('[SKIP] Persisted round-trip proof already exists; no model was called.')
            return
        async with ModelGateway.from_env() as gateway:
            perception = prepared.document['receipt']
            if perception.get('provider') != 'openai' or perception.get('requested_model') != perception.get('routed_model'):
                raise PreparedDataError('Prepared Evidence has no verified OpenAI perception receipt.')
            repository.save_evidence(graph.evidence, graph.entities, graph.links)
            orchestrator = build_orchestrator(gateway, repository)
            decision, loop = await orchestrator.open_loop_agent.process(graph.evidence, graph.entities)
            reasoning = receipt(gateway, gateway.reasoning_model, 'nvidia')
            if loop is None:
                raise PreparedDataError('Evidence was stored, but the real Open Loop Agent chose no loop; no hypothesis or proof was invented.')
            if repository.get_evidence(graph.evidence.evidence_id) != graph.evidence:
                raise PreparedDataError('Evidence readback differs from the canonical record.')
            if repository.get_entities([entity.entity_id for entity in graph.entities]) != graph.entities:
                raise PreparedDataError('Entity readback differs from the canonical records.')
            edges = repository.get_loop_entities([loop.loop_id])
            linked_ids = sorted({edge.entity_id for edge in edges})
            if graph.evidence not in repository.get_related_evidence(linked_ids, limit=10000):
                raise PreparedDataError('Persisted loop does not ground back to the original Evidence.')
            result = {'kind': 'real_zetaris_roundtrip', 'verified': True, 'evidence_id': graph.evidence.evidence_id,
                      'entity_ids': [entity.entity_id for entity in graph.entities], 'loop_id': loop.loop_id,
                      'loop_entity_ids': linked_ids,
                      'image_ref': graph.evidence.image_ref, 'artifact_sha256': prepared.artifact_sha256,
                      'receipts': {'perception': perception, 'reasoning': reasoning}, 'open_loop_action': decision.decision.value}
            write_private(args.output, result)
            print('[PASS] Real Evidence/entity/loop graph stored and grounded through Zetaris; application IDs preserved.')
            print('[RECEIPTS]', json.dumps(result['receipts']))


async def extract_batch(args):
    images = sorted(path for path in args.images.iterdir() if path.is_file() and path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'})
    if not images:
        raise PreparedDataError('No screenshots found in the supplied unsorted image folder.')
    if len({image.stem for image in images}) != len(images):
        raise PreparedDataError('Screenshot basenames collide; choose explicit single-image output paths without renaming originals.')
    counts = {'generated': 0, 'skipped': 0, 'failed': 0}
    for image in images:
        output = args.output / (image.stem + '.json')
        existed = output.exists()
        try:
            await extract(SimpleNamespace(image=image, output=output))
            counts['skipped' if existed else 'generated'] += 1
        except Exception:
            counts['failed'] += 1
            print(json.dumps(counts))
            raise PreparedDataError('Perception preparation stopped at the first failure; completed artifacts were preserved.') from None
    print(json.dumps(counts))


def batch(args):
    files = sorted(args.input.glob('*.json')) if args.input.is_dir() else [args.input]
    if not files:
        raise PreparedDataError('No prepared JSON files found; batch import never invokes perception.')
    prepared, failed = [], 0
    for file in files:
        try:
            prepared.append(load_prepared(file, args.images))
        except (PreparedDataError, EvidenceError):
            failed += 1
    if args.dry_run:
        print(json.dumps({'dry_run': True, 'validated': len(prepared), 'failed': failed, 'model_calls': 0}))
        if failed:
            raise PreparedDataError('Some inputs failed validation; originals were not modified.')
        return
    if failed:
        raise PreparedDataError('Batch validation failed before any write; use --dry-run to inspect counts.')
    if args.proof is None:
        raise PreparedDataError('Supply --proof from the successful one-record round-trip before batch import.')
    counts = dict(inserted=0, updated=0, skipped=0, failed=0, inserted_entities=0)
    with open_repository() as repository:
        verified_proof(args.proof, repository)
        for item in prepared:
            graph = item.graph
            current = repository.get_evidence(graph.evidence.evidence_id)
            existing = {entity.entity_id: entity for entity in repository.get_entities([entity.entity_id for entity in graph.entities])}
            try:
                repository.save_evidence(graph.evidence, graph.entities, graph.links)
                if current is not None:
                    counts['skipped'] += 1
                else:
                    counts['inserted'] += 1
                    counts['inserted_entities'] += sum(entity.entity_id not in existing for entity in graph.entities)
                    counts['updated'] += sum(entity.entity_id in existing and existing[entity.entity_id] != entity for entity in graph.entities)
            except Exception:
                counts['failed'] += 1
                print(json.dumps(counts))
                raise PreparedDataError('Batch stopped at a storage failure; inspect state before retrying. No model was called.') from None
    print(json.dumps(counts))


async def run(args):
    with open_repository() as repository:
        proof = verified_proof(args.proof, repository)
        if args.output.exists():
            raise PreparedDataError('Run output already exists; choose a new output path rather than overwrite it.')
        evidence = repository.get_evidence(proof['evidence_id'])
        entities = repository.get_entities(proof['entity_ids'])
        if args.demo_context:
            first = entities[0]
            events = [ContextEvent('ctx_demo_' + uuid.uuid4().hex[:12], ContextType.CALENDAR,
                                   'Synthetic demo meal outing', datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                   first.location_name, first.city, first.country, {'source': 'synthetic_demo_context'})]
        elif args.context:
            records = json.loads(args.context.read_text())
            events = [ContextEvent(**{**row, 'context_type': ContextType(row['context_type'])}) for row in records]
        else:
            raise PreparedDataError('Provide --context JSON or explicitly select --demo-context (synthetic calendar).')
        async with ModelGateway.from_env() as gateway:
            orchestrator = build_orchestrator(gateway, repository)
            decision, loop = await orchestrator.open_loop_agent.process(evidence, entities)
            open_loop_receipt = receipt(gateway, gateway.reasoning_model, 'nvidia')
            for event in events:
                repository.save_context_event(event)
            result = await orchestrator.evaluate_context(events)
            seen = set()
            for event in result.trace_events:
                if event.agent not in {'CONTEXT', 'CRITIC', 'OPEN_LOOP'} or event.action in {'FAILED', 'RETRY'}:
                    continue
                data = event.receipt or {}
                if data.get('requested_model') != gateway.reasoning_model or data.get('routed_model') != gateway.reasoning_model or data.get('provider') != 'nvidia':
                    raise ModelGatewayError('Run receipt validation failed; no integration success was recorded.')
                seen.add(event.agent)
            complete = {'CONTEXT', 'CRITIC'} <= seen and result.final_action.value != 'FAILED_SAFE'
            output = {'kind': 'real_zetaris_orchestrator_run', 'verified': complete, 'repository': 'ZetarisRepository',
                      'synthetic_context': args.demo_context, 'evidence_id': evidence.evidence_id,
                      'open_loop_action': decision.decision.value, 'open_loop_receipt': open_loop_receipt,
                      'result': result.to_dict()}
            write_private(args.output, output)
            print('[PASS]' if complete else '[INCOMPLETE]', 'Real stored Evidence -> Open Loop -> Context/Critic; trace and receipts saved privately.')
            print('Final action:', result.final_action.value)
            if not complete:
                raise PreparedDataError('The actual run did not execute both Context and Critic successfully; integration stays pending.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    commands = parser.add_subparsers(dest='command', required=True)
    extract_parser = commands.add_parser('extract')
    extract_parser.add_argument('--image', type=Path, required=True)
    extract_parser.add_argument('--output', type=Path, required=True)
    prepare_parser = commands.add_parser('extract-batch')
    prepare_parser.add_argument('--images', type=Path, default=ROOT / 'screenshot')
    prepare_parser.add_argument('--output', type=Path, required=True)
    for name in ('roundtrip', 'batch'):
        command = commands.add_parser(name)
        command.add_argument('--input', type=Path, required=True)
        command.add_argument('--images', type=Path, default=ROOT / 'screenshot')
        if name == 'roundtrip':
            command.add_argument('--output', type=Path, required=True)
        else:
            command.add_argument('--proof', type=Path)
            command.add_argument('--dry-run', action='store_true')
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--proof', type=Path, required=True)
    run_parser.add_argument('--output', type=Path, required=True)
    context = run_parser.add_mutually_exclusive_group(required=True)
    context.add_argument('--context', type=Path)
    context.add_argument('--demo-context', action='store_true')
    args = parser.parse_args()
    if any(not path.is_file() for path in args.env_file):
        parser.error('An explicitly supplied environment file does not exist.')
    for path in [*args.env_file, ROOT / 'backend/.env.local']:
        if path.is_file():
            load_dotenv(path, override=False)
    try:
        if sample_mode():
            raise PreparedDataError('Real data commands require SAMPLE_MODE=false; fixtures are a separate explicit mode.')
        if args.command == 'batch':
            batch(args)
        else:
            asyncio.run({'extract': extract, 'extract-batch': extract_batch, 'roundtrip': roundtrip, 'run': run}[args.command](args))
        return 0
    except (PreparedDataError, EvidenceError, ModelGatewayError, ZetarisError) as exc:
        print('[BLOCKED]', str(exc))
        return 1
    except Exception as exc:
        print('[BLOCKED]', type(exc).__name__ + '; details withheld to protect credentials and source content.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
