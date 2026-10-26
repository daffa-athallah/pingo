"""GET /runs, /api/runs/{id} and /agent-events/{id}: the runs of the ACTIVE workspace only.

Canonical mode additionally lists the curated runs saved by backend/scripts (context_eval, revision_fixture). Demo and sample workspaces never read
those files or each other's runs, so one mode can not show another mode's activity.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.app.runs import summary

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
router = APIRouter()
MAX_RUNS = 20


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def curated_runs() -> dict[str, dict]:
    """Curated live runs from backend/scripts, adapted to the run-record shape. Canonical workspace only."""
    runs = {}
    folder = RUNTIME / 'context_eval'
    for path in sorted(folder.glob('context-eval-*.json')):
        report = _read(path)
        for name, scenario in report.get('scenarios', {}).items():
            result = scenario.get('result', {})
            if result.get('run_id'):
                events = result.get('trace_events', [])
                runs[result['run_id']] = {
                    'run_id': result['run_id'], 'kind': 'context_critic', 'scenario': name, 'label': name, 'provenance': 'live',
                    'workspace': 'canonical', 'synthetic_inputs': bool(scenario.get('synthetic')), 'status': 'done',
                    'started_at': (events[0] or {}).get('timestamp') if events else None, 'finished_at': None, 'source_file': path.name,
                    'context_event': scenario.get('context_event'), 'loop_title': report.get('loop_title'), 'result': result}
    for path in sorted(folder.glob('revision-fixture-*.json')):
        report = _read(path)
        result = report.get('result', {})
        if result.get('run_id'):
            events = result.get('trace_events', [])
            runs[result['run_id']] = {
                'run_id': result['run_id'], 'kind': 'revision_fixture', 'scenario': 'revision', 'label': 'revision', 'provenance': 'live',
                'workspace': 'canonical', 'synthetic_inputs': True, 'status': 'done',
                'started_at': (events[0] or {}).get('timestamp') if events else None, 'finished_at': None, 'source_file': path.name,
                'original_title': report.get('original_title'), 'final_title': report.get('final_title'), 'result': result}
    return runs


def latest_curated() -> list[dict]:
    """The newest run per scenario that already records its repository reads."""
    latest = {}
    for run in curated_runs().values():
        events = run['result'].get('trace_events', [])
        if run['kind'] == 'context_critic' and not any(e.get('agent') == 'ZETARIS' for e in events):
            continue  # older runs saved before repository reads were traced
        key = run['scenario']
        if key not in latest or run['source_file'] > latest[key]['source_file']:
            latest[key] = run
    return [latest[key] for key in ('A_relevant', 'B_restraint', 'revision') if key in latest]


def workspace_runs(request: Request, *, limit: int = MAX_RUNS) -> list[dict]:
    """Runs of the active workspace, newest first. Curated runs are appended only in the canonical workspace."""
    records = request.app.state.runs.list()[:limit]
    if request.app.state.workspace == 'canonical':
        records = records + latest_curated()
    return records


@router.get('/runs')
def runs(request: Request):
    return [summary(r) for r in workspace_runs(request)]


def find_run(request: Request, run_id: str) -> dict | None:
    record = request.app.state.runs.get(run_id)
    if record is None and request.app.state.workspace == 'canonical':
        record = curated_runs().get(run_id)
    return record


@router.get('/api/runs/{run_id}')
def run_detail(request: Request, run_id: str):
    """One run with its events so far. A client polls this while status is 'running'."""
    record = find_run(request, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail='Run not found.')
    return summary(record)


@router.get('/agent-events/{run_id}')
def agent_events(request: Request, run_id: str):
    record = find_run(request, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail='Run not found.')
    return record['result'].get('trace_events', [])
