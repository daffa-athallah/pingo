#!/usr/bin/env python3
"""Phase 2: run the existing OpenLoopAgent over real Evidence stored in Zetaris, one record at a time.

Evidence is read through ZetarisRepository in a stable order and never modified. Each eligible record gets one
agent call (Nemotron via Nightshift); the agent's own decision is applied with its own apply() semantics and
persisted back to Zetaris. Nothing about the expected intention is hardcoded.

Resumable/idempotent: a private ledger (backend/runtime/open_loops/ledger.json) records every processed Evidence
ID, so a rerun makes no model call for it. New loop IDs are derived from the Evidence ID, so a crash between
persisting and writing the ledger cannot create a second loop on replay.

Local policy (explicit, no model call): sensitive Evidence, and domains outside SUPPORTED_DOMAINS, are skipped.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import real_env
from real_env import ROOT, real_repository
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.adapters.zetaris import ZetarisError
from backend.app.agents.open_loop import OpenLoopAgent, OpenLoopError
from backend.app.domain.models import LoopStatus
from backend.app.domain.trace import TraceEvent

# Product domains for this hackathon. 'travel' is the canonical destination domain the Evidence Agent emits.
SUPPORTED_DOMAINS = frozenset({'food', 'shopping', 'travel'})
RUNTIME = ROOT / 'backend/runtime/open_loops'
LEDGER = RUNTIME / 'ledger.json'
EXPECTED_PROVIDER_HINT = 'nvidia'


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def loop_id_for(evidence_id: str, generation: int = 0) -> str:
    """Stable per Evidence. A reprocess bumps the generation so a retired loop's links are never inherited."""
    key = evidence_id if generation == 0 else f'{evidence_id}#{generation}'
    return 'loop_' + hashlib.sha256(key.encode()).hexdigest()[:12]


def load_ledger() -> dict:
    if LEDGER.is_file():
        return json.loads(LEDGER.read_text())
    return {}


def save_ledger(ledger: dict) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix('.tmp')
    tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True))
    tmp.replace(LEDGER)


def receipt_of(gateway) -> dict | None:
    routing = dict(getattr(gateway, 'last_routing', None) or {})
    return {k: routing.get(k) for k in ('requested_model', 'routed_model', 'provider')} if routing else None


def eligibility(evidence) -> str | None:
    if evidence.sensitive:
        return 'SKIP_SENSITIVE'
    if evidence.domain not in SUPPORTED_DOMAINS:
        return 'SKIP_UNSUPPORTED_DOMAIN'
    return None


async def process(args) -> int:
    ledger = load_ledger()
    run_id = 'run_ol_' + hashlib.sha256(now().encode()).hexdigest()[:10]
    events: list[TraceEvent] = []

    def trace(agent, action, reason, refs=(), next_step=None, output_ref=None, receipt=None):
        events.append(TraceEvent(agent, action, reason, list(refs), next_step, output_ref, run_id, now(), receipt))

    counts = Counter()
    with real_repository() as repo:
        all_evidence = repo.list_evidence()
        todo = [e for e in all_evidence if args.only is None or e.evidence_id in args.only]
        generations: dict[str, int] = {}
        if args.reprocess:
            if not args.only:
                raise ZetarisError('--reprocess requires --only with explicit Evidence IDs.')
            RUNTIME.mkdir(parents=True, exist_ok=True)
            (RUNTIME / f'ledger.backup-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json').write_text(json.dumps(ledger, indent=2, sort_keys=True))
            for evidence in todo:
                entry = ledger.pop(evidence.evidence_id, None)
                generations[evidence.evidence_id] = (entry or {}).get('generation', 0) + 1
                # Only a loop this Evidence itself created is retired. Evidence is never touched, and the loop is INVALIDATED
                # (hidden from retrieval and surfacing) rather than deleted, so history stays inspectable.
                if entry and entry.get('outcome') == 'CREATE' and entry.get('loop_id') == loop_id_for(evidence.evidence_id, entry.get('generation', 0)):
                    with repo.unit_of_work():
                        repo.update_open_loop(entry['loop_id'], status=LoopStatus.INVALIDATED, updated_at=now())
                    print(f'[RESET] {evidence.evidence_id}: invalidated {entry["loop_id"]} "{entry.get("proposed_title")}"')
            save_ledger(ledger)
        trace('ZETARIS', 'LOAD', f'Loaded {len(all_evidence)} Evidence records from Zetaris.', [], 'OPEN_LOOP')
        print(f'[INFO] {len(all_evidence)} Evidence in Zetaris; {len(ledger)} already in ledger')
        async with ModelGateway.from_env() as gateway:
            agent_ids = {}
            agent = OpenLoopAgent(gateway, repo, new_id=lambda: agent_ids['next'])
            calls = 0
            for evidence in todo:
                eid = evidence.evidence_id
                if eid in ledger:
                    counts['ALREADY_PROCESSED'] += 1
                    continue
                skip = eligibility(evidence)
                if skip:
                    ledger[eid] = {'outcome': skip, 'domain': evidence.domain, 'at': now()}
                    counts[skip] += 1
                    trace('OPEN_LOOP', skip, f'Not reasoned over locally ({skip.removeprefix("SKIP_").lower().replace("_", " ")}).',
                          [f'evidence:{eid}'], 'STOP')
                    print(f'[SKIP] {eid} domain={evidence.domain} sensitive={evidence.sensitive} -> {skip}')
                    continue
                if args.limit is not None and calls >= args.limit:
                    counts['DEFERRED_BY_LIMIT'] += 1
                    continue
                links = repo.get_evidence_entities([eid])
                entities = repo.get_entities(sorted({k.entity_id for k in links}))
                refs = [f'evidence:{eid}'] + [f'entity:{e.entity_id}' for e in entities]
                related = repo.get_related_evidence([e.entity_id for e in entities], exclude_evidence_ids=[eid])
                trace('ZETARIS', 'RETRIEVE', f'Loaded {len(entities)} entities and {len(related)} other supporting Evidence records from Zetaris.',
                      refs, 'OPEN_LOOP')
                if args.dry_run:
                    print(f'[PLAN] {eid} domain={evidence.domain} entities={len(entities)} related_evidence={len(related)}')
                    continue
                generation = generations.get(eid, 0)
                agent_ids['next'] = loop_id_for(eid, generation)
                decision, receipt, error = None, None, None
                for attempt in range(2):  # one call plus at most one retry, as in the orchestrator
                    gateway.last_routing = {}
                    try:
                        calls += 1
                        decision = await agent.decide(evidence, entities)
                        receipt = receipt_of(gateway)
                        break
                    except (OpenLoopError, ModelGatewayError) as exc:
                        error = str(exc)
                        trace('OPEN_LOOP', 'RETRY' if attempt == 0 else 'FAILED', f'Call failed ({error}).', refs, 'OPEN_LOOP' if attempt == 0 else 'STOP')
                if decision is None:
                    counts['FAILED'] += 1
                    print(f'[FAIL] {eid}: {error}')  # not ledgered: a rerun will retry it
                    continue
                with repo.unit_of_work():
                    loop = agent.apply(decision)
                kind = decision.decision.value
                counts[kind] += 1
                trace('OPEN_LOOP', kind, decision.concise_reason, refs, 'STOP', f'loop:{loop.loop_id}' if loop else None, receipt)
                ledger[eid] = {
                    'outcome': kind, 'domain': evidence.domain, 'generation': generation, 'loop_id': loop.loop_id if loop else None,
                    'target_loop_id': decision.target_loop_id, 'proposed_title': decision.proposed_title,
                    'confidence': decision.confidence, 'concise_reason': decision.concise_reason,
                    'supporting_evidence_ids': decision.supporting_evidence_ids,
                    'supporting_entity_ids': decision.supporting_entity_ids,
                    'material_uncertainty': decision.material_uncertainty, 'receipt': receipt, 'at': now()}
                save_ledger(ledger)
                print(f'[{kind}] {eid} -> {loop.loop_id if loop else "-"} "{decision.proposed_title or ""}" conf={decision.confidence} receipt={receipt}')
        save_ledger(ledger) if not args.dry_run else None
    counts['MODEL_CALLS'] = calls
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        (RUNTIME / f'trace-{stamp}.jsonl').write_text('\n'.join(json.dumps(e.to_dict(), ensure_ascii=False) for e in events))
    print('[SUMMARY]', dict(counts))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--limit', type=int, help='maximum model calls this run (for step-wise inspection)')
    parser.add_argument('--only', nargs='+', help='restrict to these Evidence IDs')
    parser.add_argument('--reprocess', action='store_true', help='with --only: retire the loops these Evidence records created, then reason over them again')
    parser.add_argument('--dry-run', action='store_true', help='read Zetaris and show the plan; no model calls, no writes')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
        return asyncio.run(process(args))
    except (ZetarisError, ModelGatewayError) as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
