#!/usr/bin/env python3
"""Live smoke: Context Agent -> Critic Agent, each via Nightshift -> NVIDIA reasoning model.

Synthetic data only. Does not hardcode the model's answers: it validates schema, supplied IDs,
decision invariants and the routing receipt, then prints sanitized results and trace events.
"""
import asyncio
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.context import ContextAgent, ContextDecision, ContextDecisionKind, ContextError
from backend.app.agents.critic import CriticAgent, CriticError, CriticKind
from backend.app.domain.models import ContextEvent, ContextType, Entity, Evidence, LoopStatus, OpenLoop

NOW = '2026-10-25T17:00:00+00:00'
CARLTON = OpenLoop('loop_carlton', 'Try restaurants in Carlton', 'food', LoopStatus.OPEN, 0.7, '2026-10-20T10:00:00+00:00', '2026-10-24T10:00:00+00:00')
RESTAURANTS = [Entity(f'ent_c{i}', 'restaurant', 'food', n, location_name='Carlton', city='Melbourne', country='Australia')
               for i, n in enumerate(('Brunetti', 'Tiamo', 'Seven Seeds'))]
CARLTON_EVIDENCE = [Evidence(f'ev_c{i}', 'screenshot', 'food', f'Saved post about {n}, a Carlton restaurant.', f'2026-10-2{i}T10:00:00+00:00', False, 'high')
                    for i, n in enumerate(('Brunetti', 'Tiamo', 'Seven Seeds'))]
DINNER = ContextEvent('ctx_dinner', ContextType.CALENDAR, 'Dinner with Alex', '2026-10-25T19:00:00+00:00', 'Carlton', 'Melbourne', 'Australia')
DRY_CLEANING = ContextEvent('ctx_errand', ContextType.CALENDAR, 'Pick up dry cleaning', '2026-10-25T08:30:00+00:00', 'Carlton', 'Melbourne', 'Australia')
ZARA = Evidence('ev_zara', 'screenshot', 'shopping', 'Zara product page showing a brown jacket.', '2026-10-24T10:00:00+00:00', False, 'high')
BUY = OpenLoop('loop_buy', 'Buy this Zara jacket tomorrow', 'shopping', LoopStatus.OPEN, 0.6, '2026-10-24T10:00:00+00:00', '2026-10-24T10:00:00+00:00')
JACKET = [Entity('ent_jacket', 'product', 'shopping', 'Brown jacket', brand='Zara')]
TODAY = ContextEvent('ctx_mall', ContextType.CALENDAR, 'Shopping trip', '2026-10-25T14:00:00+00:00', 'Chadstone', 'Melbourne', 'Australia')


def verify_receipt(gateway: ModelGateway, label: str) -> dict:
    routing = dict(gateway.last_routing)
    model = gateway.reasoning_model
    if routing.get('requested_model') != model or routing.get('routed_model') != model or routing.get('provider') != 'nvidia':
        raise ModelGatewayError(f'{label} receipt does not show NVIDIA serving the requested reasoning model.')
    return routing


def check_invariants(decision, loop_id, evidence_ids, context_ids) -> None:
    if decision.loop_id not in (loop_id, None) or not set(decision.supporting_evidence_ids) <= evidence_ids \
            or not set(decision.supporting_context_ids) <= context_ids:
        raise CriticError('Critic cited an id that was not supplied.')
    if decision.decision == CriticKind.SURFACE and not (decision.supporting_evidence_ids and decision.supporting_context_ids):
        raise CriticError('SURFACE without a cited evidence/context chain.')


async def main_async() -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    models_used = 0
    async with ModelGateway.from_env() as gateway:
        context_agent, critic = ContextAgent(gateway, now=lambda: NOW), CriticAgent(gateway)
        cases = [
            ('A', 'strong candidate: Carlton restaurants + dinner in Carlton', CARLTON, RESTAURANTS, CARLTON_EVIDENCE, [DINNER], None),
            ('B', 'restraint: weak Carlton MATCH on a dry-cleaning errand', CARLTON, RESTAURANTS, CARLTON_EVIDENCE, [DRY_CLEANING],
             ContextDecision(ContextDecisionKind.MATCH, 'loop_carlton', ContextType.LOCATION, ['ctx_errand'], 0.35, 'The errand is also in Carlton.')),
            ('C', 'over-specific loop: "Buy this Zara jacket tomorrow" from one screenshot', BUY, JACKET, [ZARA], [TODAY],
             ContextDecision(ContextDecisionKind.MATCH, 'loop_buy', ContextType.CALENDAR, ['ctx_mall'], 0.7, 'Shopping trip today.')),
        ]
        for label, title, loop, entities, evidence, events, forced in cases:
            print(f'[SCENARIO {label}] {title}')
            context = forced
            if context is None:  # scenario A runs the real Context Agent first
                context = await context_agent.assess([loop], {loop.loop_id: entities}, events)
                print('  context routing: ' + ', '.join(f'{k}={v}' for k, v in verify_receipt(gateway, 'Context').items()))
                models_used += 1
            print(f'  context: {context.decision.value}  trigger: {context.trigger_type.value if context.trigger_type else None}')
            decision = await critic.review(context, loop, entities, evidence, events)
            check_invariants(decision, loop.loop_id, {e.evidence_id for e in evidence}, {e.context_id for e in events})
            if decision.decided_by == 'model':
                print('  critic routing: ' + ', '.join(f'{k}={v}' for k, v in verify_receipt(gateway, 'Critic').items()))
                models_used += 1
            print('  critic: ' + json.dumps({k: (v.value if hasattr(v, 'value') else v) for k, v in vars(decision).items() if v not in (None, [])},
                                            ensure_ascii=False))
            print(f'  next_step: {decision.next_step.value}')
            print('  trace: ' + json.dumps(decision.trace().to_dict(), ensure_ascii=False))
    if models_used < 3:
        raise ModelGatewayError('Too few model-backed calls were verified.')
    print(f'[PASS] {models_used} reasoning calls were served by NVIDIA through Nightshift; schema, ids and invariants verified')
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except (ModelGatewayError, ContextError, CriticError) as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] Critic smoke failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
