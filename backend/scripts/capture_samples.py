#!/usr/bin/env python3
"""Capture final Nightshift replies and H-MEM I/O on isolated snapshots. No canonical API/JDBC access.

Requires live Nightshift and a dedicated H-MEM sidecar named by --hmem-url.
Synthetic images come from upload_e2e.py, never personal credentials or images.
Review generated files before sharing. Replay requires Python only, no Node/models.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.app.adapters.nightshift import ModelGateway
from backend.app.demo_workspace import open_demo_repository
from backend.app.hmem import HMemClient, seed_from_repository
from backend.app.recorded import CapturingGateway, DIRECTORY
from backend.app.sample_cases import CASES, IMAGES, MemoryTape, execute_case, NOW
from upload_e2e import CASES as IMAGE_CASES, screenshot


async def run(args):
    load_dotenv(ROOT / 'backend/.env', override=False)
    IMAGES.mkdir(parents=True, exist_ok=True)
    for case, (_, lines) in zip(('attach', 'create', 'sensitive'), IMAGE_CASES):
        # Fake credential screenshot deliberately excluded from the public bundle.
        if case == 'sensitive':
            lines = ['SYNTHETIC PRIVACY TEST', 'Medical record', 'Patient: Example Person', 'Diagnosis: example only', 'Not a real medical record']
        (IMAGES / f'{case}.png').write_bytes(screenshot(lines))
    for case in args.cases or CASES:
        memory = None
        if case in ('attach', 'create'):
            client = HMemClient(args.hmem_url)
            client.reset()  # dedicated sidecar only, never :8300
            seed_from_repository(client, open_demo_repository())
            memory = MemoryTape(inner=client)
        async with ModelGateway.from_env() as live:
            capture = CapturingGateway(live)
            try:
                record = await execute_case(case, capture, memory=memory, provenance='live')
            except Exception:
                failed = ROOT / 'backend/runtime/recording_failures'
                failed.mkdir(parents=True, exist_ok=True)
                (failed / f'{case}.json').write_text(json.dumps(capture.calls, indent=2))
                raise
            bundle = {'case': case, 'clock': NOW, 'captured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'vision_model': live.vision_model, 'reasoning_model': live.reasoning_model,
                      'calls': capture.calls, 'memory_calls': memory.calls if memory else [],
                      'input_label': 'Synthetic test input over historical snapshot; real Nightshift model decisions',
                      'observed_action': record['result']['final_action']}
        (DIRECTORY / f'{case}.json').write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + '\n')
        print(case, record['result']['final_action'], 'calls=', len(capture.calls), 'error=', record['result']['error'], flush=True)
        print([(e['agent'], e['action']) for e in record['result']['trace_events']], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hmem-url', default='http://127.0.0.1:8317', choices=['http://127.0.0.1:8317'])
    parser.add_argument('cases', nargs='*', choices=list(CASES))
    args = parser.parse_args()
    asyncio.run(run(args))
