#!/usr/bin/env python3
"""Write the five documented examples: input_examples/, output_examples/ and logs/examples/ (JSON Lines traces).

Outputs are exported from recorded runs of the real agents (see backend/demo/recordings/README.md). No model is called here."""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['RECALL_LOG_DIR'] = 'off'
from backend.app.sample_cases import CASES, replay_case
from backend.app.tracelog import lines

EXAMPLES = [
    ('example_1_attach', 'attach', 'A new screenshot of a venue you already saved is attached to the existing intention.'),
    ('example_2_revision', 'revision', 'The Critic rejects an over-specific intention and the Open Loop Agent revises it before anything surfaces.'),
    ('example_3_surface', 'surface', 'A calendar event near a saved place: the Context Agent matches, the Critic approves a reminder with its evidence.'),
    ('example_4_restraint', 'restraint', 'An unrelated calendar event: no saved intention matches, so Recall stays silent.'),
    ('example_5_checkin', 'duplicates', 'Look-alike saves: the Critic merges one pair, keeps others apart, and asks you about the pair it is unsure of.'),
]
CONTEXT = {'surface': ('Dinner with Alex', 'Fitzroy North'), 'restraint': ('Pick up dry cleaning', 'Fitzroy North')}


def input_example(name, case, note):
    base = {'name': name, 'what_it_shows': note}
    if case == 'attach':
        return {**base, 'endpoint': 'POST /api/screenshots', 'body': 'raw image bytes', 'image': 'backend/demo/recordings/images/attach.png',
                'curl': 'curl -X POST --data-binary @backend/demo/recordings/images/attach.png -H "Content-Type: image/png" http://localhost:8000/api/screenshots?wait=1'}
    if case in CONTEXT:
        title, place = CONTEXT[case]
        body = {'synthetic': True, 'events': [{'context_type': 'CALENDAR', 'title': title, 'occurs_at': '2026-10-26T20:00:00+11:00',
                                               'location_name': place, 'city': 'Melbourne', 'country': 'Australia'}]}
        return {**base, 'endpoint': 'POST /api/context/evaluate', 'body': body,
                'curl': f"curl -X POST -H 'Content-Type: application/json' -d '{json.dumps(body)}' http://localhost:8000/api/context/evaluate"}
    if case == 'revision':
        return {**base, 'endpoint': 'python backend/scripts/revision_fixture.py', 'fixture': 'a saved intention retitled "Book a table at OMB Burger tonight at 8pm" (nothing supports the time or booking), then a Melbourne CBD calendar event'}
    return {**base, 'endpoint': 'python backend/scripts/consolidation_fixture.py', 'fixture': 'backend/demo/recordings/duplicate_input.json (six synthetic look-alike intentions)'}


async def main():
    for folder in ('input_examples', 'output_examples', 'logs/examples'):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    for name, case, note in EXAMPLES:
        record = await replay_case(case)
        result = record['result']
        output = {'name': name, 'provenance': record['provenance'], 'workspace': record['workspace'], 'synthetic_inputs': record['synthetic_inputs'],
                  'note': 'Exported from a recorded run of the real agents; model replies were captured from Nightshift (receipts describe the capture).',
                  'final_action': result['final_action'], 'revision_count': result['revision_count'], 'verification_count': result['verification_count'],
                  'message_payload': result['message_payload'], 'question': result['question'], 'outcome': record.get('outcome'),
                  'check_ins': record.get('check_ins'), 'consolidation': record.get('consolidation'), 'surface': record.get('surface'),
                  'agents_in_trace': sorted({e['agent'] for e in result['trace_events']}), 'trace_events': len(result['trace_events'])}
        (ROOT / 'input_examples' / f'{name}.json').write_text(json.dumps(input_example(name, case, note), indent=2, ensure_ascii=False) + '\n')
        (ROOT / 'output_examples' / f'{name}.json').write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
        (ROOT / 'logs/examples' / f'{name}.jsonl').write_text(''.join(json.dumps(l, ensure_ascii=False) + '\n' for l in lines(record)))
        print(f"{name}: {result['final_action']} ({len(result['trace_events'])} events)")


if __name__ == '__main__':
    asyncio.run(main())
