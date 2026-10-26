"""Agent traces as JSON Lines: one line per agent event, written when a run finishes and echoed to stdout.

    logs/trace.jsonl  (override the folder with RECALL_LOG_DIR; RECALL_LOG_DIR=off disables the file)

Each line: timestamp, trace_id (the run), agent_name, action, input_summary, output_summary, target_agent (the agent or step that received the
result), confidence, retry_count, status, plus provenance (live | recorded | mixed), workspace and the model receipt. It is derived from the same
events the UI shows, so it never contains model reasoning, image data or credentials.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys

log = logging.getLogger('recall.trace')
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

STATUS = {'FAILED': 'failed', 'FAILED_SAFE': 'failed', 'RETRY': 'retrying', 'REQUEST_REVISION': 'needs_revision', 'VERIFY_CONTEXT': 'needs_validation',
          'ASK': 'needs_input', 'QUEUED': 'waiting'}
KEY_ACTIONS = {'EXTRACT', 'ATTACH', 'CREATE', 'REVISE', 'RESOLVE', 'IGNORE', 'MATCH', 'NO_MATCH', 'NEEDS_VERIFICATION', 'SURFACE', 'STAY_SILENT', 'ASK',
               'REQUEST_REVISION', 'VERIFY_CONTEXT', 'MERGE', 'KEEP_SEPARATE', 'RETRY', 'FAILED', 'FAILED_SAFE', 'QUERY', 'STORE'}


def log_dir() -> Path | None:
    configured = os.environ.get('RECALL_LOG_DIR', '').strip()
    if configured.lower() == 'off' or 'unittest' in sys.argv[0]:
        return None
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / 'logs'


def lines(record: dict) -> list[dict]:
    out, retries = [], 0
    for event in record['result']['trace_events']:
        if event['action'] == 'RETRY':
            retries += 1
        detail = event.get('detail') or {}
        receipt = event.get('receipt') or {}
        out.append({
            'timestamp': event.get('timestamp') or record.get('started_at'), 'trace_id': record['run_id'], 'agent_name': event['agent'],
            'action': event['action'], 'input_summary': ', '.join(event.get('input_refs') or []) or record.get('label', ''),
            'output_summary': event['reason'], 'target_agent': event.get('next_step'), 'confidence': detail.get('confidence'),
            'retry_count': retries, 'status': STATUS.get(event['action'], 'success'),
            'provenance': record.get('provenance'), 'workspace': record.get('workspace'),
            'model': receipt.get('routed_model'), 'provider': receipt.get('provider')})
    return out


def write(record: dict) -> None:
    """Never raises: logging must not affect a run."""
    try:
        entries = lines(record)
        for entry in entries:
            if entry['action'] in KEY_ACTIONS:
                log.info('[%s] %s %s -> %s: %s', entry['trace_id'], entry['agent_name'], entry['action'], entry['target_agent'] or 'END', entry['output_summary'][:160])
        folder = log_dir()
        if folder is not None and entries:
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'trace.jsonl').open('a') as handle:
                handle.writelines(json.dumps(entry, ensure_ascii=False) + '\n' for entry in entries)
    except Exception:  # noqa: BLE001
        pass
