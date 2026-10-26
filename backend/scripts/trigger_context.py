#!/usr/bin/env python3
"""Send one synthetic context event through Pingo's real Context/Critic workflow.

This script never makes a model decision. The backend loads real Open Loops and
Evidence, then the existing orchestrator calls Context Agent and Critic Agent.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def aware(value: str, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise ValueError('Use an IANA timezone such as Australia/Melbourne.') from None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError('Use ISO date/time, for example 2026-11-02T12:30:00+11:00.') from None
    if result.tzinfo is None or result.utcoffset() is None:
        result = result.replace(tzinfo=zone)
    return result


def now(timezone_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        raise ValueError('Use an IANA timezone such as Australia/Melbourne.') from None


def payload(args) -> dict:
    observed = aware(args.at, args.timezone) if args.at else now(args.timezone)
    common = {
        'context_id': 'ctx_script_' + uuid.uuid4().hex[:16],
        'source': 'SIMULATED',
        'type': args.kind.upper(),
        'timestamp': observed.isoformat(),
        'timezone': args.timezone,
    }
    if args.kind == 'location':
        if not -90 <= args.latitude <= 90 or not -180 <= args.longitude <= 180:
            raise ValueError('Latitude must be -90..90 and longitude -180..180.')
        if args.accuracy < 0:
            raise ValueError('Accuracy must be zero or greater.')
        common['title'] = args.label or 'Simulated location'
        common['location'] = {
            'latitude': args.latitude,
            'longitude': args.longitude,
            'accuracy_meters': args.accuracy,
            'name': args.label,
        }
    elif args.kind == 'calendar':
        start, end = aware(args.start, args.timezone), aware(args.end, args.timezone)
        if end <= start:
            raise ValueError('Calendar end must be after start.')
        common.update({
            'title': args.title,
            'start_time': start.isoformat(),
            'end_time': end.isoformat(),
            'description': args.description,
            'location': {'name': args.location, 'city': args.city, 'country': args.country},
        })
    else:
        common['title'] = args.label or 'Simulated current time'
    return {'now': observed.isoformat(), 'events': [common]}


def endpoint(base: str) -> str:
    base = base.strip().rstrip('/')
    if not base.startswith(('http://', 'https://')):
        raise ValueError('API base must start with http:// or https://.')
    return base + '/context-simulator/evaluate'


def send(url: str, body: dict) -> dict:
    request = Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    # Direct tailnet access should not be routed through a machine-wide HTTP proxy.
    with build_opener(ProxyHandler({})).open(request, timeout=600) as response:
        return json.load(response)


def report(result: dict) -> None:
    run = result.get('result') or {}
    print('Evaluation:', result.get('evaluation_id'))
    print('Final action:', run.get('final_action') or result.get('state'))
    print('Delivery:', result.get('delivery'))
    print('Notification:', result.get('notification_id') or 'none')
    print('Agents:')
    traces = run.get('trace_events') or []
    if not traces:
        print('  none (no eligible active loop, or evaluation failed safely)')
    for trace in traces:
        receipt = trace.get('receipt') or {}
        routed = f" via {receipt.get('provider')}/{receipt.get('routed_model')}" if receipt else ''
        print(f"  {trace.get('agent')} -> {trace.get('action')} -> {trace.get('next_step') or 'STOP'}{routed}")
        print(f"    {trace.get('reason')}")
    if result.get('error') or run.get('error'):
        print('Safe error:', result.get('error') or run.get('error'))


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument('--api-base', default=os.environ.get('PINGO_API_BASE_URL', ''),
                       help='Backend origin, e.g. https://device.tailnet.ts.net:8443')
    value.add_argument('--timezone', default='Australia/Melbourne')
    value.add_argument('--dry-run', action='store_true', help='Print validated JSON; do not contact the backend')
    modes = value.add_subparsers(dest='kind', required=True)
    location = modes.add_parser('location')
    location.add_argument('--latitude', type=float, required=True)
    location.add_argument('--longitude', type=float, required=True)
    location.add_argument('--accuracy', type=float, default=20)
    location.add_argument('--label', default='')
    location.add_argument('--at')
    calendar = modes.add_parser('calendar')
    calendar.add_argument('--title', required=True)
    calendar.add_argument('--start', required=True)
    calendar.add_argument('--end', required=True)
    calendar.add_argument('--location', default='')
    calendar.add_argument('--city', default='')
    calendar.add_argument('--country', default='')
    calendar.add_argument('--description', default='')
    calendar.add_argument('--at')
    clock = modes.add_parser('time')
    clock.add_argument('--at', required=True)
    clock.add_argument('--label', default='')
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        body = payload(args)
        if args.dry_run:
            print(json.dumps(body, indent=2, ensure_ascii=False))
            return 0
        if not args.api_base:
            raise ValueError('Set PINGO_API_BASE_URL or pass --api-base.')
        report(send(endpoint(args.api_base), body))
        return 0
    except HTTPError as error:
        detail = f'HTTP {error.code}'
        try:
            message = json.load(error).get('detail')
            if isinstance(message, str):
                detail += ': ' + message
        except Exception:
            pass
        print('[FAILED]', detail)
    except URLError as error:
        print('[FAILED] Backend is unreachable through the configured URL.')
    except (ValueError, TimeoutError) as error:
        print('[FAILED]', str(error))
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
