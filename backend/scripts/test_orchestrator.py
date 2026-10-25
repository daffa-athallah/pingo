#!/usr/bin/env python3
"""Live golden smoke for the RecallOrchestrator, using real agents through Nightshift.

Part 1: real screenshot -> Evidence (vision model) -> ingestion -> Open Loop (NVIDIA)
        -> synthetic calendar event -> Context (NVIDIA) -> Critic (NVIDIA).
Part 2: revision demonstration. A synthetic over-specific loop is seeded in the repository; the
        agents then run for real. If the Critic does not choose REQUEST_REVISION live, that is
        reported, and the deterministic offline tests remain the proof of the branch.

Every model-backed trace event must carry a receipt for the configured model and expected provider.
No secrets, image data or chain-of-thought are printed.
"""
import argparse
import asyncio
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.evidence import Entity, Evidence, Location
from backend.app.domain.models import ContextEvent, ContextType, LoopEntity, LoopStatus, OpenLoop
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.orchestration.recall import RecallOrchestrator, RunResult
from backend.app.repositories.memory import InMemoryLoopRepository

MODEL_AGENTS = {'EVIDENCE', 'OPEN_LOOP', 'CONTEXT', 'CRITIC'}
SKIPPED = {'RETRY', 'FAILED'}


def verify_receipts(result: RunResult, gateway: ModelGateway, vision_provider: str) -> int:
    checked = 0
    for event in result.trace_events:
        if event.agent not in MODEL_AGENTS or event.action in SKIPPED:
            continue
        expected_model, expected_provider = ((gateway.vision_model, vision_provider) if event.agent == 'EVIDENCE'
                                             else (gateway.reasoning_model, 'nvidia'))
        r = event.receipt or {}
        if r.get('requested_model') != expected_model or r.get('routed_model') != expected_model or r.get('provider') != expected_provider:
            raise ModelGatewayError(f'{event.agent} {event.action} has no matching receipt for {expected_model}/{expected_provider}.')
        checked += 1
    return checked


def show(result: RunResult) -> None:
    print(f'[RUN] {result.run_id} {result.run_type.value} -> {result.final_action.value}'
          f'  revisions={result.revision_count} verifications={result.verification_count}'
          + (f'  loop={result.loop_id}' if result.loop_id else '') + (f'  error={result.error}' if result.error else ''))
    for e in result.trace_events:
        r = e.receipt or {}
        who = f"{r['provider']}/{r['routed_model']}" if r else 'no model call'
        print(f'  {e.agent:<9} {e.action:<17} next={e.next_step:<10} {who}')
        print(f'    reason: {e.reason}')
    if result.message_payload:
        print(f'  payload: {result.message_payload}')


async def run(args) -> int:
    load_dotenv(ROOT / 'backend/.env', override=False)
    all_events = []
    async with ModelGateway.from_env() as gateway:
        repo = InMemoryLoopRepository()
        orchestrator = RecallOrchestrator.from_gateway(gateway, repo)

        print('[PART 1] golden path: real screenshot -> loop -> synthetic calendar context')
        stored = await orchestrator.ingest_screenshot(args.image)
        show(stored)
        total = verify_receipts(stored, gateway, args.vision_provider)
        all_events += stored.trace_events
        if stored.final_action.value != 'STORED' or not stored.loop_id:
            raise ModelGatewayError('Golden path did not store a loop; cannot continue to context.')
        loop = repo.loops[stored.loop_id]
        entity = repo.entities[next(l.entity_id for l in repo.loop_entities if l.loop_id == loop.loop_id)]
        place = entity.city or entity.location_name or 'Melbourne'
        event = ContextEvent('ctx_supper', ContextType.CALENDAR, f'Late supper with Sam in {place}', '2026-10-25T22:30:00+00:00',
                             entity.location_name, entity.city, entity.country)
        decided = await orchestrator.evaluate_context([event])
        show(decided)
        total += verify_receipts(decided, gateway, args.vision_provider)
        all_events += decided.trace_events

        if not args.skip_revision_demo:
            print('[PART 2] revision demonstration: seeded over-specific loop, real agents')
            demo = InMemoryLoopRepository()
            result = ingest(Evidence('shopping', 'Zara product page showing a brown jacket.', [
                Entity('Brown jacket', 'product', brand='Zara')], False, 'high'), demo, new_id=lambda: 'ev_zara',
                captured_at='2026-10-24T10:00:00+00:00')
            demo.save_open_loop(OpenLoop('loop_buy', 'Buy this Zara jacket tomorrow', 'shopping', LoopStatus.OPEN, 0.6,
                                         '2026-10-24T10:00:00+00:00', '2026-10-24T10:00:00+00:00'))
            for e in result.entities:
                demo.link_loop_entity(LoopEntity('loop_buy', e.entity_id, 'subject', 0.6))
            mall = ContextEvent('ctx_mall', ContextType.CALENDAR, 'Shopping trip', '2026-10-25T14:00:00+00:00',
                                'Chadstone', 'Melbourne', 'Australia')
            revised = await RecallOrchestrator.from_gateway(gateway, demo).evaluate_context([mall])
            show(revised)
            total += verify_receipts(revised, gateway, args.vision_provider)
            all_events += revised.trace_events
            if revised.revision_count:
                print('[INFO] The revision branch executed live: Open Loop and Critic were called again.')
            else:
                print('[INFO] The Critic did not request a revision in this live run; see offline tests for the deterministic branch proof.')
    if args.jsonl:
        args.jsonl.write_text('\n'.join(__import__('json').dumps(e.to_dict(), ensure_ascii=False) for e in all_events) + '\n')
        print(f'[INFO] Trace written to {args.jsonl}')
    print(f'[PASS] {total} model-backed trace events carried matching receipts through Nightshift')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT / 'screenshot/IMG_8922.PNG')
    parser.add_argument('--vision-provider', default='openai')
    parser.add_argument('--jsonl', type=Path)
    parser.add_argument('--skip-revision-demo', action='store_true')
    try:
        return asyncio.run(run(parser.parse_args()))
    except ModelGatewayError as exc:
        print('[FAIL] ' + str(exc))
        return 1
    except Exception:
        print('[FAIL] Orchestrator smoke failed; credentials and raw payloads were not logged.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
