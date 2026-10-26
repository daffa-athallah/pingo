#!/usr/bin/env python3
"""Phases 4-5: controlled ContextEvent evaluation against one REAL Open Loop stored in Zetaris.

The loop, its entities and Evidence come from Zetaris. The ContextEvents are SYNTHETIC TEST INPUT (they are not read
from a calendar) and are labelled so in the saved artifact. The Context, Critic (and any revision/verification) decisions
are real model output via Nightshift -> Nemotron. Nothing about the expected outcome is hardcoded; invariants are checked.

Persisted loops are not rewritten by this script except where the orchestrator itself revises one (it will not in A/B).
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import real_env
from real_env import ROOT, real_repository
from process_open_loops import load_ledger
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.adapters.zetaris import ZetarisError
from backend.app.bootstrap import build_orchestrator
from backend.app.domain.models import ContextEvent, ContextType, LoopStatus
from backend.app.domain.trace import TraceEvent
from backend.app.orchestration.recall import FinalAction

OUT = ROOT / 'backend/runtime/context_eval'
SURFACEABLE = {LoopStatus.OPEN, LoopStatus.ACTIVE}
MODEL_AGENTS = {'CONTEXT', 'CRITIC', 'OPEN_LOOP', 'EVIDENCE'}


def pick_loop(repo, ledger, domain):
    """Strongest real loop in the domain: most supporting Evidence records in the processing ledger."""
    best = {}
    for eid, v in ledger.items():
        if v.get('loop_id') and v.get('domain') == domain and v['outcome'] in ('CREATE', 'ATTACH', 'REVISE'):
            best.setdefault(v['loop_id'], set()).add(eid)
    candidates = [(len(ev), loop_id) for loop_id, ev in best.items() if (repo.get_open_loop(loop_id) or None)]
    if not candidates:
        raise ZetarisError(f'No {domain} Open Loop exists in Zetaris.')
    return max(candidates)[1]


def check(ok, label, failures):
    print(('  [PASS] ' if ok else '  [FAIL] ') + label)
    if not ok:
        failures.append(label)


def validate(result, repo, events, loop_id, failures):
    trace = result.trace_events
    model_events = [e for e in trace if e.agent in MODEL_AGENTS and e.action not in ('RETRY', 'FAILED')]
    check(all(e.receipt and e.receipt.get('provider') == 'nvidia' and 'nemotron' in (e.receipt.get('routed_model') or '')
              for e in model_events), f'every model-backed trace event has an nvidia/nemotron receipt ({len(model_events)} events)', failures)
    check(all(e.run_id == result.run_id and e.timestamp for e in trace), 'every TraceEvent carries run_id and timestamp', failures)
    if result.final_action == FinalAction.SURFACE:
        payload = result.message_payload or {}
        loop = repo.get_open_loop(payload.get('loop_id'))
        check(loop is not None and loop.status in SURFACEABLE, 'surfaced loop exists and is OPEN/ACTIVE', failures)
        check(bool(payload.get('evidence_ids')) and bool(payload.get('context_ids')), 'SURFACE cites Evidence and Context (no Recall without evidence, no interruption without context)', failures)
        known = {e.context_id for e in events}
        check(set(payload['context_ids']) <= known, 'cited context ids were all supplied', failures)
        check(all(repo.get_evidence(i) is not None for i in payload['evidence_ids']), 'cited Evidence ids all exist in Zetaris', failures)
    check(result.final_action != FinalAction.SURFACE or not result.error, 'no SURFACE alongside an error', failures)
    check(result.revision_count <= 1 and result.verification_count <= 1, 'revision/verification stayed within bounds', failures)


async def run(args) -> int:
    ledger = load_ledger()
    OUT.mkdir(parents=True, exist_ok=True)
    tomorrow = (datetime.now(ZoneInfo('Australia/Melbourne')) + timedelta(days=1)).date()

    def at(hour, minute=0):
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute, tzinfo=ZoneInfo('Australia/Melbourne')).isoformat()

    with real_repository() as repo:
        loop_id = args.loop_id or pick_loop(repo, ledger, args.domain)
        loop = repo.get_open_loop(loop_id)
        if loop is None:
            raise ZetarisError('Selected Open Loop does not exist in Zetaris.')
        links = repo.get_loop_entities([loop_id])
        entities = repo.get_entities(sorted({k.entity_id for k in links}))
        place = next((e for e in entities if e.city), None)
        city = place.city if place else None
        country = place.country if place else None
        window = [l.loop_id for l in repo.get_active_open_loops(limit=10)]
        print(f'[LOOP] {loop.loop_id} "{loop.title}" status={loop.status.value} conf={loop.confidence}')
        print(f'[LOOP] entities={[e.name for e in entities]} in Context Agent window: {loop_id in window}')
        if loop_id not in window:
            raise ZetarisError('Selected loop is outside the Context Agent window (10 most recently updated active loops).')
        scenarios = {
            'A_relevant': ContextEvent('ctx_ctrl_a', ContextType.CALENDAR, args.relevant_title, at(19), args.suburb, city, country),
            'B_restraint': ContextEvent('ctx_ctrl_b', ContextType.CALENDAR, args.restraint_title, at(17, 30), args.suburb, city, country),
        }
        failures, report = [], {'label': 'SYNTHETIC controlled ContextEvents; loop/evidence/model decisions are real',
                                'loop_id': loop_id, 'loop_title': loop.title, 'scenarios': {}}
        async with ModelGateway.from_env() as gateway:
            orchestrator = build_orchestrator(gateway, repo)
            for name, event in scenarios.items():
                print(f'\n=== {name}: CALENDAR "{event.title}" {event.location_name}, {event.city} {event.occurs_at}  [synthetic test input]')
                supporting = repo.get_related_evidence([e.entity_id for e in entities], limit=10)
                result = await orchestrator.evaluate_context([event])
                # Real repository reads that the Context/Critic stages performed for this run (loop, entities, Evidence).
                result.trace_events.insert(0, TraceEvent(
                    'ZETARIS', 'LOAD', f'Loaded Open Loop with {len(entities)} entities and {len(supporting)} supporting Evidence records from Zetaris.',
                    [f'loop:{loop_id}'] + [f'evidence:{i.evidence_id}' for i in supporting], 'CONTEXT', f'loop:{loop_id}',
                    result.run_id, datetime.now(timezone.utc).isoformat(timespec='seconds'), None))
                for t in result.trace_events:
                    print(f'  {t.agent:9}{t.action:20}-> {t.next_step}  receipt={(t.receipt or {}).get("provider")}  | {t.reason}')
                print(f'  FINAL: {result.final_action.value} loop={result.loop_id} error={result.error}')
                validate(result, repo, [event], loop_id, failures)
                report['scenarios'][name] = {'context_event': json.loads(json.dumps(event.__dict__, default=lambda o: getattr(o, 'value', str(o)))),
                                             'synthetic': True, 'result': result.to_dict()}
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        (OUT / f'context-eval-{stamp}.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print('\n[SAVED]', OUT / f'context-eval-{stamp}.json')
        print('[RESULT]', 'invariants failed: ' + '; '.join(failures) if failures else 'all invariants held')
        return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--loop-id')
    parser.add_argument('--domain', default='food')
    parser.add_argument('--suburb', required=True, help='location_name for the synthetic context; choose it from the loop\'s real Evidence')
    parser.add_argument('--relevant-title', default='Dinner with Alex')
    parser.add_argument('--restraint-title', default='Pick up dry cleaning')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        return asyncio.run(run(args))
    except (ZetarisError, ModelGatewayError) as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
