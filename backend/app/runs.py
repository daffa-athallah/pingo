"""Run records for everything the UI can watch: screenshot uploads and context evaluations.

A run is a list of structured events (agent, action, reason, refs, receipt and an optional `detail` of structured inputs, retrievals, decisions
and state changes). Events are appended while the run executes, so a client can poll and see progress. No model reasoning is ever recorded.

Every run says where it came from:
  provenance  'live'      real models answered (Nightshift)
              'scripted'  the credential-free sample fixture answered
              'recorded'  reserved: a captured real run replayed through the unchanged agents
  workspace   'canonical' the real Zetaris data, 'demo' the resettable in-memory demo workspace, 'sample' the offline fixture
Runs of different workspaces never share storage, so one mode cannot show another mode's runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock

from backend.app import tracelog

PROVENANCE = ('live', 'scripted', 'recorded')
WORKSPACES = ('canonical', 'demo', 'sample')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class RunRecorder:
    def __init__(self, store: 'RunStore', record: dict):
        self._store, self.record = store, record

    @property
    def run_id(self) -> str:
        return self.record['run_id']

    def emit(self, agent: str, action: str, reason: str, *, input_refs=(), next_step=None, output_ref=None, receipt=None, detail=None) -> dict:
        with self._store._lock:
            events = self.record['result']['trace_events']
            event = {'run_id': self.run_id, 'seq': len(events) + 1, 'timestamp': _now(), 'agent': agent, 'action': action, 'reason': reason,
                     'input_refs': list(input_refs), 'next_step': next_step, 'output_ref': output_ref, 'receipt': receipt, 'detail': detail}
            events.append(event)
            return event

    def update_result(self, **fields) -> None:
        with self._store._lock:
            self.record['result'].update(fields)

    def finish(self, final_action: str, *, error: str | None = None, **fields) -> dict:
        with self._store._lock:
            self.record['result'].update(final_action=final_action, error=error, **fields)
            self.record['status'] = 'failed' if final_action == 'FAILED_SAFE' else 'done'
            self.record['finished_at'] = _now()
        self._store._persist(self.record)
        tracelog.write(self.record)
        return self.record


class RunStore:
    def __init__(self, workspace: str, directory: Path | None = None):
        if workspace not in WORKSPACES:
            raise ValueError('Unknown workspace.')
        self.workspace, self.directory = workspace, directory
        self._runs: dict[str, dict] = {}
        self._lock = RLock()

    def start(self, run_id: str, *, kind: str, provenance: str, run_type: str, label: str, synthetic_inputs: bool = False, **meta) -> RunRecorder:
        if provenance not in PROVENANCE:
            raise ValueError('Unknown provenance.')
        record = {'run_id': run_id, 'kind': kind, 'label': label, 'provenance': provenance, 'workspace': self.workspace,
                  'synthetic_inputs': synthetic_inputs, 'status': 'running', 'started_at': _now(), 'finished_at': None, **meta,
                  'result': {'run_id': run_id, 'run_type': run_type, 'final_action': None, 'loop_id': None, 'evidence_id': None,
                             'message_payload': None, 'question': None, 'error': None, 'revision_count': 0, 'verification_count': 0,
                             'trace_events': []}}
        with self._lock:
            self._runs[run_id] = record
        return RunRecorder(self, record)

    def add_finished(self, record: dict) -> None:
        """Register an already complete run (a scripted sample run, or one read from disk)."""
        with self._lock:
            self._runs[record['run_id']] = record

    def save_finished(self, record: dict) -> None:
        self.add_finished(record)
        self._persist(record)

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            if run_id in self._runs:
                return self._runs[run_id]
        if self.directory is not None:
            path = (self.directory / f'{run_id}.json').resolve()
            if path.parent == self.directory.resolve() and path.is_file():
                try:
                    record = json.loads(path.read_text())
                except ValueError:
                    return None
                return record if record.get('workspace') == self.workspace else None
        return None

    def list(self) -> list[dict]:
        """Newest first. Includes runs persisted by earlier server processes in this workspace."""
        found = {}
        if self.directory is not None and self.directory.is_dir():
            for path in self.directory.glob('run_*.json'):
                try:
                    record = json.loads(path.read_text())
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get('workspace') == self.workspace and 'result' in record:
                    found[record['run_id']] = record
        with self._lock:
            found.update(self._runs)
        return sorted(found.values(), key=lambda r: (r.get('started_at') or '', r['run_id']), reverse=True)

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()
        if self.directory is not None and self.directory.is_dir():
            for path in self.directory.glob('run_*.json'):
                path.unlink(missing_ok=True)

    def _persist(self, record: dict) -> None:
        if self.directory is None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f'{record["run_id"]}.tmp'
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        temporary.replace(self.directory / f'{record["run_id"]}.json')


def summary(record: dict, *, include_events: bool = True) -> dict:
    """The shape served by GET /runs."""
    out = {k: v for k, v in record.items() if k != 'result'}
    out['result'] = record['result'] if include_events else {k: v for k, v in record['result'].items() if k != 'trace_events'}
    return out
