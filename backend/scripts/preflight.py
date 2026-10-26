#!/usr/bin/env python3
"""Demo preflight: PASS/WARN/FAIL for everything the demo depends on, with the command that fixes each failure.

Checks Colima, the Zetaris containers and data, Nightshift and the model route, the backend API, Tailscale (including that no Funnel exposes it
publicly), auto-start jobs and sleep prevention. Read-only; no secrets are printed. `--model` adds one tiny real model call. `--quick` skips
the Zetaris JDBC and model checks. Exit code 1 if anything FAILs.
"""
import argparse
import asyncio
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

import real_env
from real_env import ROOT

API = 'http://127.0.0.1:8000'
TAILSCALE_PORT = 8443
RESULTS: list[tuple[str, str]] = []


def report(level: str, name: str, detail: str = '', fix: str = '') -> None:
    RESULTS.append((level, name))
    print(f'[{level}] {name}' + (f': {detail}' if detail else ''))
    if fix and level != 'PASS':
        print(f'       FIX: {fix}')


def run(args, timeout=20) -> tuple[int, str]:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return done.returncode, (done.stdout + done.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, type(exc).__name__


def find(*candidates) -> str | None:
    return next((p for p in (shutil.which(c) or (c if Path(c).exists() else None) for c in candidates) if p), None)


def port_open(port: int, host='127.0.0.1') -> bool:
    with socket.socket() as s:
        s.settimeout(3)
        return s.connect_ex((host, port)) == 0


def http(url: str, timeout=60) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b''
    except Exception:  # noqa: BLE001
        return 0, b''


def check_docker() -> None:
    colima = find('colima', '/opt/homebrew/bin/colima')
    if not colima:
        return report('FAIL', 'Colima', 'not installed', 'brew install colima docker')
    code, _ = run([colima, 'status'], 15)
    if code != 0:
        return report('FAIL', 'Colima', 'not running', 'colima start --memory 8')
    report('PASS', 'Colima', 'running')
    docker = find('docker', '/opt/homebrew/bin/docker')
    code, out = run([docker or 'docker', 'ps', '--format', '{{.Names}}|{{.Status}}'], 20)
    rows = dict(line.split('|', 1) for line in out.splitlines() if '|' in line and line.startswith('zetaris-'))
    needed = ['zetaris-postgres-1', 'zetaris-driver-1', 'zetaris-api-1', 'zetaris-ui-1']
    bad = [n for n in needed if n not in rows or 'unhealthy' in rows[n] or 'Up' not in rows[n]]
    if bad:
        report('FAIL', 'Zetaris containers', 'not healthy: ' + ', '.join(bad), f'cd {ROOT / "zetaris-platform"} && docker compose up -d && ./verify.sh')
    else:
        report('PASS', 'Zetaris containers', f'{len(needed)} up')


def check_zetaris(deep: bool) -> None:
    if not port_open(10000):
        return report('FAIL', 'Zetaris JDBC', 'port 10000 closed', f'cd {ROOT / "zetaris-platform"} && docker compose up -d (wait for healthy)')
    if not deep:
        return report('PASS', 'Zetaris JDBC', 'port 10000 open (data not checked with --quick)')
    try:
        from real_env import real_repository
        with real_repository() as repo:
            counts = {t: repo.connection.query(f'SELECT COUNT(*) FROM recall_data.app.{t}')[0][0]
                      for t in ('evidence', 'entities', 'evidence_entities', 'check_ins')}
            # INVALIDATED rows are retired history, not live loops.
            counts['active_loops'] = repo.connection.query("SELECT COUNT(*) FROM recall_data.app.open_loops WHERE status IN ('OPEN', 'ACTIVE')")[0][0]
    except Exception as exc:  # noqa: BLE001
        return report('FAIL', 'Zetaris data', type(exc).__name__ + ' while reading recall_data.app', 'check env.local (JDBC URL/JAR/JAVA_HOME) and that the schema exists')
    if counts['evidence'] < 1 or counts['active_loops'] < 1:
        return report('FAIL', 'Zetaris data', str(counts), 'import Evidence (backend/SAVED_EVIDENCE_IMPORT.md) and run process_open_loops.py')
    report('PASS', 'Zetaris data', ', '.join(f'{k}={v}' for k, v in counts.items()))


async def _nightshift(model_call: bool) -> None:
    from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
    try:
        async with ModelGateway.from_env() as gateway:
            models = await gateway.available_models()
            missing = [m for m in (gateway.reasoning_model, gateway.vision_model) if m and m not in models]
            if missing:
                return report('FAIL', 'Nightshift models', 'not advertised: ' + ', '.join(missing), 'check METERLESS_*_MODEL in env.local / backend/.env')
            report('PASS', 'Nightshift', f'reachable, {len(models)} models, reasoning={gateway.reasoning_model}')
            if model_call:
                gateway.last_routing = {}
                nonce = uuid.uuid4().hex[:8]
                await gateway.complete([{'role': 'user', 'content': f'Reply with exactly: OK {nonce}'}], max_tokens=1024, model=gateway.reasoning_model)
                routing = gateway.last_routing
                ok = routing.get('provider') == 'nvidia' and 'nemotron' in (routing.get('routed_model') or '')
                report('PASS' if ok else 'FAIL', 'Model route', f"{routing.get('routed_model')} via {routing.get('provider')}",
                       'Nightshift must route the reasoning model to NVIDIA Nemotron')
    except ModelGatewayError as exc:
        report('FAIL', 'Nightshift', str(exc), 'open the "Nightshift M1-M4" app; check METERLESS_BASE_URL / METERLESS_API_KEY')


def check_backend() -> None:
    status, body = http(API + '/health', 10)
    if status != 200:
        return report('FAIL', 'Backend API', 'not answering on :8000', 'launchctl kickstart -k gui/$(id -u)/com.recall.backend   (or: deploy/install_launchd.sh install)')
    health = json.loads(body)
    if health.get('mode') != 'real' or health.get('repository') != 'ZetarisRepository':
        return report('FAIL', 'Backend mode', f"{health.get('mode')}/{health.get('repository')}", 'restart the backend without SAMPLE_MODE')
    report('PASS', 'Backend API', 'real mode, ZetarisRepository')
    status, body = http(API + '/open-loops', 90)
    loops = json.loads(body) if status == 200 else []
    report('PASS' if loops else 'FAIL', 'Open Loops via API', f'{len(loops)} loops', 'backend cannot read Zetaris; check the Zetaris checks above')
    status, _ = http(API + '/api/check-ins', 30)
    report('PASS' if status == 200 else 'FAIL', 'Check-in API', f'HTTP {status}', 'check backend log: ~/Library/Logs/recall/backend.log')
    try:  # an empty POST is rejected with 400 before anything is read, sent to a model or stored: it only proves the route exists
        code = urllib.request.urlopen(urllib.request.Request(API + '/api/screenshots', data=b'', method='POST'), timeout=15).status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception:  # noqa: BLE001
        code = 0
    report('PASS' if code == 400 else 'FAIL', 'Screenshot upload route', f'HTTP {code} (400 expected for an empty body)',
           'the backend is running old code: launchctl kickstart -k gui/$(id -u)/com.recall.backend')
    if loops and loops[0]['screenshots']:
        status, _ = http(API + loops[0]['screenshots'][0]['image_url'] + '?w=300', 30)
        report('PASS' if status == 200 else 'FAIL', 'Screenshot images', f'HTTP {status}', 'is the screenshot/ folder present? (RECALL_SCREENSHOT_DIR)')


def check_tailscale() -> None:
    ts = find('tailscale', '/Applications/Tailscale.app/Contents/MacOS/Tailscale')
    if not ts:
        return report('FAIL', 'Tailscale', 'not installed', 'install Tailscale and sign in')
    code, out = run([ts, 'status', '--json'])
    try:
        status = json.loads(out)
    except ValueError:
        return report('FAIL', 'Tailscale', 'daemon not answering', 'open the Tailscale app and connect')
    if status.get('BackendState') != 'Running':
        return report('FAIL', 'Tailscale', f"state {status.get('BackendState')}", 'open the Tailscale app and connect')
    dns = (status['Self'].get('DNSName') or '').rstrip('.')
    report('PASS', 'Tailscale', f'running as {dns}')
    _, serve = run([ts, 'serve', 'status'])
    if 'Funnel on' in serve:
        report('FAIL', 'Tailscale Funnel', 'a Funnel exposes this machine to the PUBLIC internet', f'{ts} funnel reset   (this API has no authentication)')
    else:
        report('PASS', 'Tailscale Funnel', 'off (tailnet only)')
    if f':{TAILSCALE_PORT}' not in serve or '8000' not in serve:
        report('FAIL', 'Tailscale serve', f'nothing serves :{TAILSCALE_PORT} -> :8000', f'{ts} serve --bg --https={TAILSCALE_PORT} http://localhost:8000')
    else:
        code, _ = http(f'https://{dns}:{TAILSCALE_PORT}/health', 20)
        report('PASS' if code == 200 else 'FAIL', 'Tailnet HTTPS URL', f'https://{dns}:{TAILSCALE_PORT} -> HTTP {code}',
               'backend down, or HTTPS certificates not enabled in the Tailscale admin console (DNS page)')
    peers = [p.get('HostName') for p in status.get('Peer', {}).values() if p.get('Online')]
    report('PASS' if peers else 'WARN', 'Tailnet peers online', ', '.join(peers) or 'none', 'ask the other person to open Tailscale')


def check_host() -> None:
    _, loaded = run(['launchctl', 'list'])
    for label, why in (('com.recall.backend', 'backend auto-start/restart'), ('com.recall.caffeinate', 'sleep prevention'),
                       ('com.recall.colima', 'Colima auto-start'), ('com.recall.daily-checkins', 'daily Check-in job')):
        report('PASS' if label in loaded else 'WARN', f'launchd {label}', why, 'deploy/install_launchd.sh install')
    _, assertions = run(['pmset', '-g', 'assertions'])
    awake = 'caffeinate' in assertions and 'PreventUserIdleSystemSleep' in assertions
    report('PASS' if awake else 'WARN', 'Sleep prevention', 'caffeinate is active' if awake else 'laptop may sleep',
           'deploy/install_launchd.sh install   (or: caffeinate -im &)')
    _, batt = run(['pmset', '-g', 'batt'])
    if 'Battery Power' in batt:
        report('WARN', 'Power', 'on battery', 'plug in the charger (caffeinate -s only holds on AC; closing the lid still sleeps the Mac)')
    else:
        report('PASS', 'Power', 'on AC')
    runs = sorted((ROOT / 'backend/runtime/consolidation').glob('run_cons_*.json')) if (ROOT / 'backend/runtime/consolidation').exists() else []
    if runs:
        import time
        age = (time.time() - runs[-1].stat().st_mtime) / 3600
        report('PASS' if age < 36 else 'WARN', 'Daily Check-in job', f'last run {age:.0f}h ago', 'backend/.venv/bin/python backend/scripts/daily_check_ins.py')
    else:
        report('WARN', 'Daily Check-in job', 'never run', 'backend/.venv/bin/python backend/scripts/daily_check_ins.py')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.add_argument('--model', action='store_true', help='also make one tiny real model call through Nightshift')
    parser.add_argument('--quick', action='store_true', help='skip the Zetaris JDBC and model checks')
    args = parser.parse_args()
    try:
        real_env.load_env(args.env_file)
    except Exception as exc:  # noqa: BLE001
        report('FAIL', 'Environment', str(exc))
    print('Recall demo preflight\n')
    check_docker()
    check_zetaris(deep=not args.quick)
    if not args.quick:
        asyncio.run(_nightshift(args.model))
    check_backend()
    check_tailscale()
    check_host()
    counts = {level: sum(1 for l, _ in RESULTS if l == level) for level in ('PASS', 'WARN', 'FAIL')}
    print(f"\n{counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail")
    print('READY FOR DEMO' if counts['FAIL'] == 0 else 'NOT READY: fix the FAIL lines above')
    return 1 if counts['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
