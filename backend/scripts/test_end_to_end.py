#!/usr/bin/env python3
"""Live end-to-end: screenshot -> Evidence Agent -> ingestion -> Open Loop Agent, via Nightshift.

Verifies from Nightshift's receipts that perception ran on the vision provider and
reasoning ran on NVIDIA. Prints a sanitized trace only: no secrets, image data, or reasoning.
"""
import argparse
import asyncio
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.evidence import EvidenceAgent, EvidenceError
from backend.app.agents.open_loop import OpenLoopAgent, OpenLoopError
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.repositories.memory import InMemoryLoopRepository


def check(routing: dict, requested: str, provider_ok, label: str) -> None:
    if routing.get('requested_model') != requested or routing.get('routed_model') != requested or not provider_ok(routing.get('provider')):
        raise ModelGatewayError(f'{label} receipt does not match the requested model/provider.')


async def run(args) -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    repository = InMemoryLoopRepository()
    async with ModelGateway.from_env() as gateway:
        extraction = await EvidenceAgent(gateway).observe(args.image)
        vision_routing = dict(gateway.last_routing)
        check(vision_routing, gateway.vision_model, lambda p: p == args.vision_provider, 'Perception')
        ingested = ingest(extraction, repository, image_ref=args.image.name)
        decision, loop = await OpenLoopAgent(gateway, repository).process(ingested.evidence, ingested.entities)
        reasoning_routing = dict(gateway.last_routing)
        check(reasoning_routing, gateway.reasoning_model, lambda p: p == 'nvidia', 'Reasoning')

    print('Evidence Agent')
    print('  action: EXTRACT')
    for entity in extraction.entities:
        print(f'  entity: {entity.name}')
    print(f'  domain: {extraction.domain}  sensitive: {extraction.sensitive}  confidence: {extraction.confidence}')
    print(f'  model: {vision_routing["routed_model"]}  provider: {vision_routing["provider"]}')
    print('Ingestion')
    print(f'  evidence_id: {ingested.evidence.evidence_id}')
    print(f'  entity_ids: {[e.entity_id for e in ingested.entities]}')
    print('Open Loop Agent')
    print(f'  action: {decision.decision.value}')
    print(f'  proposed_title: {decision.proposed_title}')
    print(f'  supporting_evidence_ids: {decision.supporting_evidence_ids}')
    print(f'  model: {reasoning_routing["routed_model"]}  provider: {reasoning_routing["provider"]}')
    print(f'  loop_id: {loop.loop_id if loop else None}')
    print('[PASS] perception on ' + vision_routing['provider'] + ', reasoning on nvidia, both through Nightshift')
    if args.show_result:
        print(f'  reason: {decision.concise_reason}')
        print(f'  uncertainty: {decision.material_uncertainty}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--vision-provider', default='openai')
    parser.add_argument('--show-result', action='store_true')
    try:
        return asyncio.run(run(parser.parse_args()))
    except (ModelGatewayError, EvidenceError, OpenLoopError) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] End-to-end run failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
