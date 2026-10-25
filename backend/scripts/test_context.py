#!/usr/bin/env python3
"""Live smoke: Context Agent -> Nightshift -> METERLESS_REASONING_MODEL -> NVIDIA provider.

Synthetic loops and calendar data only; no screenshot or user data. Prints sanitized routing
evidence and structured decisions. Chain-of-thought is never shown.
"""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.context import ContextAgent, ContextError
from backend.app.domain.models import ContextEvent, ContextType, Entity, LoopStatus, OpenLoop

LOOPS = [OpenLoop('loop_carlton', 'Try restaurants in Carlton', 'food', LoopStatus.OPEN, 0.7,
                  '2026-10-20T10:00:00+00:00', '2026-10-24T10:00:00+00:00'),
         OpenLoop('loop_tokyo', 'Places to visit in Tokyo', 'travel', LoopStatus.ACTIVE, 0.6,
                  '2026-10-10T10:00:00+00:00', '2026-10-18T10:00:00+00:00')]
ENTITIES = {
    'loop_carlton': [Entity(f'ent_c{i}', 'restaurant', 'food', name, location_name='Carlton', city='Melbourne', country='Australia')
                     for i, name in enumerate(('Brunetti', 'Tiamo', 'Seven Seeds'))],
    'loop_tokyo': [Entity('ent_t1', 'venue', 'travel', 'TeamLab Planets', city='Tokyo', country='Japan'),
                   Entity('ent_t2', 'area', 'travel', 'Shibuya', city='Tokyo', country='Japan')],
}
SCENARIOS = {
    'calendar dinner in Carlton': [ContextEvent('ctx_cal', ContextType.CALENDAR, 'Dinner with Alex',
                                                '2026-10-25T19:00:00+00:00', 'Carlton', 'Melbourne', 'Australia')],
    'unrelated dentist visit': [ContextEvent('ctx_dentist', ContextType.CALENDAR, 'Dentist appointment',
                                             '2026-10-25T09:00:00+00:00', 'Parramatta', 'Sydney', 'Australia')],
}


async def run() -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    async with ModelGateway.from_env() as gateway:
        agent = ContextAgent(gateway, now=lambda: '2026-10-25T17:00:00+00:00')
        results = []
        for name, events in SCENARIOS.items():
            decision = await agent.assess(LOOPS, ENTITIES, events)
            routing = dict(gateway.last_routing)
            if routing.get('provider') != 'nvidia' or routing.get('routed_model') != gateway.reasoning_model \
                    or routing.get('requested_model') != gateway.reasoning_model:
                raise ModelGatewayError('Receipt does not show NVIDIA serving the requested reasoning model.')
            results.append((name, decision, routing))
    for name, decision, routing in results:
        print(f'[SCENARIO] {name}')
        print('[INFO] routing evidence: ' + ', '.join(f'{k}={v}' for k, v in routing.items()))
        print(json.dumps({k: (v.value if hasattr(v, 'value') else v) for k, v in asdict(decision).items()}, indent=2, ensure_ascii=False))
    print('[PASS] Context reasoning was served by NVIDIA through Nightshift')
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except (ModelGatewayError, ContextError) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] Context smoke failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
