#!/usr/bin/env python3
"""Phase 6: exercise Critic REQUEST_REVISION -> Open Loop REVISE -> Critic with a CONTROLLED, LABELLED FIXTURE.

Real Evidence and Entities are read from Zetaris, then copied into a throwaway in-memory repository together with ONE
deliberately over-specific loop (synthetic fixture: states a time and action the Evidence does not show). The persisted
Zetaris dataset is never written to. The Context/Critic/Open Loop decisions are real Nightshift -> Nemotron output; the
expected branch is NOT hardcoded, so the outcome is reported as it happens.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import real_env
from real_env import ROOT, real_repository
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.adapters.zetaris import ZetarisError
from backend.app.bootstrap import build_orchestrator
from backend.app.domain.models import ContextEvent, ContextType, LoopEntity, LoopStatus, OpenLoop
from backend.app.repositories.memory import InMemoryLoopRepository

OUT = ROOT / 'backend/runtime/context_eval'


async def run(args) -> int:
    with real_repository() as zetaris:
        entity = next((e for e in zetaris.list_entities() if args.entity.lower() in e.name.lower()), None)
        if entity is None:
            raise ZetarisError('Entity for the fixture was not found in Zetaris.')
        evidence = zetaris.get_related_evidence([entity.entity_id], limit=10)
        links = zetaris.get_evidence_entities([e.evidence_id for e in evidence])
        entities = zetaris.get_entities(sorted({k.entity_id for k in links}))
    fixture = InMemoryLoopRepository()
    for ev in evidence:
        ev_links = [k for k in links if k.evidence_id == ev.evidence_id]
        fixture.save_evidence(ev, [e for e in entities if e.entity_id in {k.entity_id for k in ev_links}], ev_links)
    tz = ZoneInfo('Australia/Melbourne')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    loop = OpenLoop('loop_fixture_overspecific', args.title, evidence[0].domain, LoopStatus.OPEN, 0.9, now, now)
    fixture.save_open_loop(loop)
    fixture.link_loop_entity(LoopEntity(loop.loop_id, entity.entity_id, 'subject', 0.9))
    day = (datetime.now(tz) + timedelta(days=args.day_offset)).date()
    event = ContextEvent('ctx_ctrl_rev', ContextType.CALENDAR, 'Dinner with Alex', datetime(day.year, day.month, day.day, 20, 0, tzinfo=tz).isoformat(),
                         entity.location_name, entity.city, entity.country)
    print(f'[FIXTURE] SYNTHETIC over-specific loop "{loop.title}" over REAL entity "{entity.name}" and {len(evidence)} real Evidence record(s) read from Zetaris')
    print('[FIXTURE] throwaway in-memory repository; Zetaris is not written to')
    async with ModelGateway.from_env() as gateway:
        orchestrator = build_orchestrator(gateway, fixture)
        result = await orchestrator.evaluate_context([event])
    for t in result.trace_events:
        print(f'  {t.agent:9}{t.action:18}-> {t.next_step}  receipt={(t.receipt or {}).get("provider")}  | {t.reason}')
    print(f'  FINAL: {result.final_action.value} revisions={result.revision_count} verifications={result.verification_count} error={result.error}')
    print(f'  fixture loop title now: "{fixture.get_open_loop(loop.loop_id).title}"')
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    path = OUT / f'revision-fixture-{stamp}.json'
    path.write_text(json.dumps({'label': 'CONTROLLED FIXTURE: over-specific loop is synthetic; evidence/entities real; decisions real',
                                'original_title': loop.title, 'final_title': fixture.get_open_loop(loop.loop_id).title,
                                'result': result.to_dict()}, indent=2, ensure_ascii=False))
    print('[SAVED]', path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--entity', default='OMB Burger')
    parser.add_argument('--day-offset', type=int, default=0, help='0 = tonight, matching a fixture title that says tonight')
    parser.add_argument('--title', default='Book a table at OMB Burger tonight at 8pm')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        return asyncio.run(run(args))
    except (ZetarisError, ModelGatewayError) as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
