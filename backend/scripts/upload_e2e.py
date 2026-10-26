#!/usr/bin/env python3
"""Acceptance run for POST /api/screenshots against a RUNNING demo workspace (serve.py --demo), with the REAL vision and reasoning models.

It resets the workspace, uploads three SYNTHETIC images drawn here (a new post about a venue Recall already knows, a venue it has not seen, and a
screenshot of fake credentials), and prints the run's events as they arrive, exactly what a UI polling GET /api/runs/{id} sees. Model decisions are
real; the expected outcomes are printed, never forced. Canonical Zetaris is not involved.
"""
import argparse
import io
import json
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

CASES = [
    ("A. NEW post about a venue Recall already knows (expect ATTACH to the Elmo's loop)",
     ["Elmo's Hamburger", 'Fitzroy North, Melbourne', 'Smashed cheeseburgers and thick shakes.', 'Open Wed to Sun, 5pm until late.', '4.6 stars from 800 reviews']),
    ('B. A venue Recall has not seen (expect CREATE)',
     ['Kiwami Ramen House', 'Lygon Street, Carlton', 'Tonkotsu broth simmered 18 hours.', 'Ramen from $16', 'Closed Mondays']),
    ('C. A screenshot of FAKE credentials (expect sensitive: nothing described, no reasoning, image deleted)',
     ['Account sign-in', 'Email: demo.user@example.com', 'Password: hunter2-Example!', 'Card: 4111 1111 1111 1111', 'CVV 123  Expiry 09/29']),
]


def screenshot(lines: list[str]) -> bytes:
    image = Image.new('RGB', (900, 1600), (250, 250, 247))
    draw, y = ImageDraw.Draw(image), 120
    for index, line in enumerate(lines):
        draw.text((60, y), line, fill=(20, 20, 20), font=ImageFont.load_default(size=64 if index == 0 else 40))
        y += 120 if index == 0 else 80
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


def call(base: str, path: str, data: bytes | None = None, method: str = 'GET', headers: dict | None = None):
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b'null')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'null')


def describe(event: dict) -> str:
    detail = event.get('detail') or {}
    extra = ''
    if event['action'] == 'EXTRACT' and not detail.get('sensitive'):
        extra = f" | {detail.get('summary', '')[:90]} | entities={[e['name'] for e in detail.get('entities', [])]}"
    elif event['action'] == 'RETRIEVE':
        extra = (f" | related evidence={[e['evidence_id'][-6:] for e in detail['related_evidence']]} candidate loops="
                 f"{[c['title'][:40] for c in detail['candidate_loops']]}")
    elif event['agent'] == 'OPEN_LOOP' and 'confidence' in detail:
        extra = (f" | confidence={detail['confidence']} target={detail['target_loop_id']} supporting evidence={len(detail['supporting_evidence_ids'])}"
                 f" entities={len(detail['supporting_entity_ids'])}")
    elif event['action'] == 'STATE':
        extra = f" | before={(detail.get('before') or {}).get('screenshots')} after={(detail.get('after') or {}).get('screenshots')}"
    receipt = event.get('receipt')
    return f"{event['agent']}:{event['action']}  {event['reason'][:100]}{extra}" + (f"  [{receipt['routed_model']} via {receipt['provider']}]" if receipt else '')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--no-reset', action='store_true')
    args = parser.parse_args()
    status, health = call(args.base, '/health')
    if status != 200 or health.get('mode') != 'demo':
        print(f'[FAIL] {args.base} is not a demo workspace (mode={health.get("mode") if health else None}). Start it with: serve.py --demo')
        return 1
    if not args.no_reset:
        print('[RESET]', call(args.base, '/api/demo/reset', b'', 'POST')[1])
    for title, lines in CASES:
        print('\n' + title)
        started = time.time()
        status, body = call(args.base, '/api/screenshots', screenshot(lines), 'POST', {'Content-Type': 'image/png'})
        print(f'  POST -> HTTP {status}, run_id={body.get("run_id")} after {time.time() - started:.1f}s')
        seen = 0
        while True:
            _, run = call(args.base, f'/api/runs/{body["run_id"]}')
            events = run['result']['trace_events']
            for event in events[seen:]:
                print(f'  +{time.time() - started:5.1f}s  {describe(event)}')
            seen = len(events)
            if run['status'] != 'running':
                break
            time.sleep(1)
        outcome = run.get('outcome') or {}
        loop = (outcome.get('open_loop') or {}).get('loop')
        print(f"  RESULT status={run['status']} provenance={run['provenance']} workspace={run['workspace']} decision={(outcome.get('open_loop') or {}).get('decision')}"
              + (f" loop=\"{loop['title']}\" screenshots={loop['screenshot_count']}" if loop else ''))
    _, loops = call(args.base, '/open-loops')
    _, runs = call(args.base, '/runs')
    print(f'\n[SUMMARY] demo workspace now lists {len(loops)} loops and {len(runs)} runs. Reset it with POST /api/demo/reset.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
