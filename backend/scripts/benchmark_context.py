#!/usr/bin/env python3
"""Does Recall interrupt at the right moments? 20 synthetic calendar events against the saved history, run through the real agents and real models.

Gold labels come from construction, not from the model: 10 events are placed where a saved intention clearly applies (SURFACE expected), 10 are
unrelated errands and appointments (STAY_SILENT expected). Each event runs on a fresh in-memory copy of the saved history; nothing is written to Zetaris.
Small and synthetic: it measures restraint and grounding, not user benefit. Needs Nightshift (METERLESS_* in backend/.env)."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.app.adapters.nightshift import ModelGateway
from backend.app.bootstrap import build_orchestrator
from backend.app.demo_workspace import open_demo_repository
from backend.app.domain.models import ContextEvent, ContextType
from backend.app.orchestration.recall import FinalAction

WHEN = '2026-11-03T19:00:00+11:00'
SHOULD_SURFACE = [  # (title, place, city, saved intention it should find)
    ('Dinner with Alex', 'Fitzroy North', 'Melbourne', 'Elmo'),
    ('Lunch catch-up near QV', 'QV Square', 'Melbourne', 'Yamamoto Udon'),
    ('Late night out in the city', 'Melbourne CBD', 'Melbourne', 'OMB Burger'),
    ('Plan the January holiday', 'Home', 'Melbourne', 'Bali flights'),
    ('Free Sunday, thinking of a day trip', 'Dandenong Ranges', 'Melbourne', 'Alfred Nicholas Garden'),
    ('Shopping trip for new shoes', 'Chadstone Shopping Centre', 'Melbourne', 'sneakers'),
    ('Start training for a 10k', 'Albert Park', 'Melbourne', 'Saucony running shoes'),
    ('Pick up skincare and makeup', 'Chemist Warehouse', 'Melbourne', 'foundation / body wash'),
    ("Sam's birthday party", 'Sam’s place', 'Melbourne', 'Ube cake'),
    ('Autumn wardrobe shopping', 'Bourke Street Mall', 'Melbourne', 'cardigans'),
]
SHOULD_STAY_SILENT = [
    ('Dentist appointment', 'Collins Street Dental', 'Melbourne'),
    ('Team standup', 'Zoom', 'Melbourne'),
    ('Pick up dry cleaning', 'Fitzroy North', 'Melbourne'),
    ('Call Mum', 'Home', 'Melbourne'),
    ('Lodge tax return', 'Home', 'Melbourne'),
    ('Car service', 'Clayton Auto', 'Melbourne'),
    ('Gym: leg day', 'Fitness First', 'Melbourne'),
    ('Return library books', 'Brunswick Library', 'Melbourne'),
    ('GP check-up', 'Carlton Medical', 'Melbourne'),
    ('Conference in Sydney', 'ICC Sydney', 'Sydney'),
]


async def run_one(gateway, title, place, city, index):
    repository = open_demo_repository()
    event = ContextEvent(f'ctx_bench_{index}', ContextType.CALENDAR, title, WHEN, place, city, 'Australia')
    result = await build_orchestrator(gateway, repository).evaluate_context([event])
    payload = result.message_payload or {}
    known = {e.evidence_id for e in repository.list_evidence()}
    cited = payload.get('evidence_ids', [])
    return {'event': title, 'place': place, 'decision': result.final_action.value, 'loop': payload.get('title'), 'reason': payload.get('reason'),
            'cites_existing_evidence': bool(cited) and all(i in known for i in cited), 'revisions': result.revision_count,
            'verifications': result.verification_count, 'agents': sorted({e.agent for e in result.trace_events}), 'error': result.error}


async def main():
    load_dotenv(ROOT / 'backend/.env', override=False)
    rows = []
    async with ModelGateway.from_env() as gateway:
        for i, (title, place, city, target) in enumerate(SHOULD_SURFACE):
            row = await run_one(gateway, title, place, city, i)
            rows.append({**row, 'expected': 'SURFACE', 'target_intention': target})
            print(f"[{i + 1:02d}/20] expect SURFACE      got {row['decision']}", flush=True)
        for j, (title, place, city) in enumerate(SHOULD_STAY_SILENT):
            row = await run_one(gateway, title, place, city, 100 + j)
            rows.append({**row, 'expected': 'STAY_SILENT', 'target_intention': None})
            print(f"[{11 + j:02d}/20] expect STAY_SILENT got {row['decision']}", flush=True)
    pos = [r for r in rows if r['expected'] == 'SURFACE']
    neg = [r for r in rows if r['expected'] == 'STAY_SILENT']
    tp = sum(r['decision'] == 'SURFACE' for r in pos)
    fp = sum(r['decision'] == 'SURFACE' for r in neg)
    surfaced = [r for r in rows if r['decision'] == 'SURFACE']
    summary = {'events': len(rows), 'true_positive': tp, 'false_negative': len(pos) - tp, 'false_positive': fp, 'true_negative': len(neg) - fp,
               'precision': round(tp / (tp + fp), 2) if tp + fp else None, 'recall': round(tp / len(pos), 2),
               'interruptions_on_unrelated_events': fp, 'surfaced_with_valid_evidence_citation': f"{sum(r['cites_existing_evidence'] for r in surfaced)}/{len(surfaced)}",
               'decisions': {d: sum(r['decision'] == d for r in rows) for d in sorted({r['decision'] for r in rows})},
               'critic_revisions_requested': sum(r['revisions'] for r in rows), 'context_verifications': sum(r['verifications'] for r in rows),
               'errors': sum(1 for r in rows if r['error'])}
    out = {'ran_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'method': __doc__.strip(), 'models': 'Recall -> Nightshift -> NVIDIA Nemotron',
           'summary': summary, 'rows': rows}
    target = ROOT / 'docs/benchmark.json'
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
