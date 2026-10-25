#!/usr/bin/env python3
"""Live smoke: Open Loop Agent -> Nightshift -> METERLESS_REASONING_MODEL -> NVIDIA provider.

Uses synthetic evidence only (no screenshot, no user data). Prints sanitized routing
evidence and the structured decision; chain-of-thought is never shown.
"""
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.open_loop import OpenLoopAgent, OpenLoopError
from backend.app.domain.models import Entity, Evidence
from backend.app.repositories.memory import InMemoryLoopRepository


async def run() -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    evidence = Evidence('ev_smoke_1', 'screenshot', 'shopping',
                        'Zara product page showing a brown jacket priced at $129.',
                        '2026-10-25T10:00:00+00:00', False, 'high')
    entities = [Entity('ent_smoke_jacket', 'product', 'shopping', 'Brown jacket', category='clothing',
                       subcategory='jacket', brand='Zara')]
    async with ModelGateway.from_env() as gateway:
        agent = OpenLoopAgent(gateway, InMemoryLoopRepository())
        decision = await agent.decide(evidence, entities)
        routing = gateway.last_routing
        requested = gateway.reasoning_model
    print(f'[INFO] requested reasoning model: {requested}')
    print('[INFO] routing evidence: ' + ', '.join(f'{k}={v}' for k, v in routing.items()))
    if routing.get('provider') != 'nvidia' or routing.get('routed_model') != requested:
        raise ModelGatewayError('Receipt does not show NVIDIA serving the requested reasoning model.')
    print('[PASS] Open Loop reasoning was served by NVIDIA through Nightshift')
    print(json.dumps({**asdict(decision), 'decision': decision.decision.value}, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except (ModelGatewayError, OpenLoopError) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] Open Loop smoke failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
