"""POST /api/screenshots: save a new screenshot from the UI; Recall perceives it and updates the Open Loops.

This is a thin HTTP and file layer over the orchestrator's existing `ingest_screenshot` (Evidence Agent -> ingestion -> Open Loop Agent). It adds no
agent logic. The run executes in the background and returns a run_id at once; the client polls GET /api/runs/{run_id} and sees structured events
(see observe.py) appear while the 30 to 40 seconds of real model calls happen.

The image is sent to the vision model through Nightshift, as every screenshot is. A screenshot the Evidence Agent flags as sensitive is stored as
Evidence (append-only, no free-form attributes), its image file is deleted, it is never reasoned over, and nothing describes it back.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app import covers
from backend.app.cover_service import ensure_cover
from backend.app.intentions_api import HiddenEvidenceRepository, read_hidden
from backend.app.location_web import find_and_save
from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.bootstrap import build_orchestrator, live_models, sample_mode
from backend.app.context_api import _gateway
from backend.app.hmem import HMemRepository
from backend.app.observe import sanitize_receipt, ObservedGateway, ObservedRepository, UploadObserver, loop_state
from backend.app.orchestration.recall import FinalAction

MAX_BYTES = 20 * 1024 * 1024  # the Evidence Agent's own limit
router = APIRouter()


def image_extension(data: bytes) -> str | None:
    """Decided from the bytes, never from the client's filename or declared type."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'webp'
    return None


def _read_index(directory: Path) -> dict:
    try:
        return json.loads((directory / 'index.json').read_text())
    except (OSError, ValueError):
        return {}


def _write_index(directory: Path, index: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / 'index.tmp'
    temporary.write_text(json.dumps(index, indent=2, sort_keys=True))
    temporary.replace(directory / 'index.json')


def _evidence_view(repository, evidence_id: str) -> dict | None:
    evidence = repository.get_evidence(evidence_id)
    if evidence is None:
        return None
    if evidence.sensitive:  # nothing about a sensitive screenshot is described back to the client
        return {'evidence_id': evidence.evidence_id, 'sensitive': True, 'domain': None, 'summary': None, 'entities': [], 'image_url': None}
    links = repository.get_evidence_entities([evidence_id])
    entities = repository.get_entities(sorted({k.entity_id for k in links}))
    return {'evidence_id': evidence.evidence_id, 'sensitive': False, 'domain': evidence.domain, 'summary': evidence.summary,
            'confidence': evidence.confidence, 'timestamp': evidence.timestamp,
            'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in entities],
            'image_url': f'/evidence/{evidence.evidence_id}/image' if evidence.image_ref else None}


def _loop_view(repository, loop_id: str | None) -> dict | None:
    state = loop_state(repository, loop_id)
    if state is None:
        return None
    entity_ids = sorted({k.entity_id for k in repository.get_loop_entities([loop_id])})
    return {**state, 'screenshot_count': state['screenshots'], 'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in repository.get_entities(entity_ids)]}


def _loop_for_evidence(repository, evidence_id: str) -> dict | None:
    links = repository.get_evidence_entities([evidence_id])
    loops = repository.get_candidate_open_loops(sorted({k.entity_id for k in links}), limit=5) if links else []
    return _loop_view(repository, loops[0].loop_id) if loops else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


WEB_RETRY = {'not_found', 'ambiguous', 'unavailable', 'stale'}  # the map's own place index did not settle these


async def _locate(state, recorder, evidence_id):
    """Post-upload lookup boundary: the map first (Ica's tool), then, for places the map's index does not know, the Location Agent
    (web search for the street address, verified on the map). Failures never undo saved Evidence."""
    from backend.app.location_lookup import enrich_evidence
    try:
        rows = await enrich_evidence(state.repository, evidence_id, emit=recorder.emit)
    except Exception:
        recorder.emit('LOCATION', 'UNAVAILABLE', 'Location search could not finish. Saved screenshots and agent decisions are preserved.', next_step='STOP')
        return []
    pending = [row for row in rows if row.get('status') in WEB_RETRY and row.get('name')]
    if pending and not sample_mode() or pending and live_models():
        try:
            async with _gateway() as gateway:
                for row in pending:
                    found = await find_and_save(state.repository, row['entity_id'], gateway, emit=lambda agent, action, reason, **kw: recorder.emit(
                        agent, action, reason, **{**kw, 'receipt': sanitize_receipt(getattr(gateway, 'last_routing', None))}))
                    if found:
                        row.update(found)
        except Exception:  # noqa: BLE001 - the web step is an extra; the map result stands
            pass
    return rows


async def _cover(state, recorder, gateway, result) -> None:
    """A new or updated single-subject intention gets a cover photo (see cover_service). Sensitive Evidence and multi-subject intentions never do."""
    try:
        if not result.loop_id or result.evidence_id is None or not (covers.provider_configured()):
            return
        repository = state.repository
        evidence = repository.get_evidence(result.evidence_id)
        loop = repository.get_open_loop(result.loop_id)
        links = repository.get_loop_entities([result.loop_id])
        entities = repository.get_entities(sorted({k.entity_id for k in links}))
        if evidence is None or evidence.sensitive or loop is None or len(entities) != 1 or entities[0].domain not in ('food', 'shopping', 'travel'):
            return
        await ensure_cover(repository, entities[0], f'{loop.title}. {evidence.summary}', ObservedGateway(gateway, UploadObserver(recorder, repository, image_ref='cover')), emit=recorder.emit)
    except Exception:  # noqa: BLE001
        pass


async def _process(state, recorder, path: Path, digest: str) -> None:
    repository = state.repository
    uploads = state.uploads_dir
    observer = UploadObserver(recorder, repository, image_ref=path.name)
    try:
        if state.write_lock.locked():
            recorder.emit('UPLOAD', 'QUEUED', 'Another screenshot is being processed; this one waits its turn (one writer at a time).',
                          input_refs=[f'image:{path.name}'], next_step='EVIDENCE')
        async with state.write_lock:
            async with _gateway() as gateway:
                observed = ObservedRepository(HiddenEvidenceRepository(repository, lambda: read_hidden(state)), observer)  # a deleted screenshot is not read back into the agents
                # H-MEM wraps OUTSIDE the observer, so the Evidence is stored (and reported) before memory is asked about it.
                agent_repository = HMemRepository(observed, state.hmem, listener=observer.memory_event) if getattr(state, 'hmem', None) else observed
                orchestrator = build_orchestrator(ObservedGateway(gateway, observer), agent_repository)
                observer.wrap_decide(orchestrator.open_loop_agent)
                result = await orchestrator.ingest_screenshot(path)
                from backend.app.checkin_clarifications import after_upload
                check_in_id = await after_upload(orchestrator.open_loop_agent, repository, observer.decision, result, recorder.emit, recorder.run_id)
                await _cover(state, recorder, gateway, result)
            if result.evidence_id is None:  # nothing was stored: do not keep an orphan file
                path.unlink(missing_ok=True)
                for event in result.trace_events:
                    if event.action in ('RETRY', 'FAILED'):
                        recorder.emit(event.agent, event.action, event.reason, input_refs=event.input_refs, next_step=event.next_step)
                message = result.error or 'The screenshot could not be processed.'
                recorder.emit('RUN', 'FAILED_SAFE', message, next_step='STOP')
                recorder.record['error_kind'] = 'processing'
                recorder.finish('FAILED_SAFE', error=message)
                return
            evidence = _evidence_view(repository, result.evidence_id)
            if evidence and evidence['sensitive']:
                path.unlink(missing_ok=True)  # the image may hold credentials or private content; Evidence is kept, the picture is not
            else:
                index = _read_index(uploads)
                index[digest] = {'evidence_id': result.evidence_id, 'file': path.name, 'at': _now()}
                _write_index(uploads, index)
            change = observer.outcome(result)
            decision = observer.decision
            recorder.record['outcome'] = {
                'status': 'stored' if result.final_action == FinalAction.STORED else 'stored_without_loop',
                'evidence': evidence,
                'open_loop': {'decision': decision.decision.value if decision else None, 'loop': _loop_view(repository, result.loop_id),
                              'reason': decision.concise_reason if decision else None, 'confidence': decision.confidence if decision else None,
                              'change': change},
                'receipts': [{'agent': e['agent'], 'action': e['action'], 'receipt': e['receipt']}
                             for e in recorder.record['result']['trace_events'] if e.get('receipt')],
                'error': result.error}
            recorder.record['outcome']['locations'] = await _locate(state, recorder, result.evidence_id) if evidence and not evidence['sensitive'] else []
            recorder.record['outcome']['check_in_id'] = check_in_id
            if result.final_action == FinalAction.STORED:
                recorder.emit('RUN', 'DONE', 'Saved. The Open Loops are up to date.', next_step='STOP', output_ref=f'loop:{result.loop_id}' if result.loop_id else None)
            else:
                recorder.emit('RUN', 'DONE', f'Evidence saved; the Open Loop step failed safely ({result.error}).', next_step='STOP')
            recorder.finish('STORED', error=result.error, loop_id=result.loop_id, evidence_id=result.evidence_id)
            if hasattr(state, 'on_data_changed'):
                state.on_data_changed()
    except ModelGatewayError as exc:
        path.unlink(missing_ok=True)
        recorder.emit('RUN', 'FAILED_SAFE', str(exc), next_step='STOP')
        recorder.record['error_kind'] = 'gateway'
        recorder.finish('FAILED_SAFE', error=str(exc))
    except Exception as exc:  # noqa: BLE001 - converted to a safe, bounded failure
        path.unlink(missing_ok=True)
        message = f'Unexpected {type(exc).__name__}'
        recorder.emit('RUN', 'FAILED_SAFE', message, next_step='STOP')
        recorder.record['error_kind'] = 'processing'
        recorder.finish('FAILED_SAFE', error=message)


@router.post('/api/screenshots')
async def upload_screenshot(request: Request, wait: int = 0):
    """Body: the raw image bytes (PNG, JPEG or WebP, at most 20 MiB), for example `fetch(url, {method: 'POST', body: file})`.
    Returns 202 with a run_id at once. `?wait=1` instead waits for the run and returns its outcome (scripts and tests)."""
    if sample_mode() and not live_models():
        raise HTTPException(status_code=501, detail='Screenshot upload needs the vision model. Configure METERLESS_BASE_URL to enable it in sample mode, or replay a bundled example.')
    declared = request.headers.get('content-length')
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status_code=413, detail='Image exceeds the 20 MiB limit.')
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail='Send the image bytes as the request body.')
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail='Image exceeds the 20 MiB limit.')
    extension = image_extension(data)
    if extension is None:
        raise HTTPException(status_code=415, detail='Unsupported image type; use PNG, JPEG or WebP.')

    state = request.app.state
    digest = hashlib.sha256(data).hexdigest()
    run_id = 'run_' + uuid.uuid4().hex[:12]
    path = state.uploads_dir / f'upload-{digest[:20]}.{extension}'
    recorder = state.runs.start(run_id, kind='screenshot_upload', provenance='live', run_type='EVIDENCE_INGESTION', label='Screenshot upload')
    received = {'bytes': len(data), 'type': extension, 'sha256': digest[:12]}

    known = _read_index(state.uploads_dir).get(digest)
    if known and state.repository.get_evidence(known['evidence_id']) is not None:  # the same image again: no model call, no second record
        recorder.emit('UPLOAD', 'DUPLICATE', 'This exact image was saved before; nothing was reprocessed.', input_refs=[f'image:{path.name}'],
                      next_step='STOP', detail={**received, 'duplicate_of': known['evidence_id']})
        recorder.record['outcome'] = {'status': 'duplicate', 'evidence': _evidence_view(state.repository, known['evidence_id']),
                                      'open_loop': {'decision': None, 'loop': _loop_for_evidence(state.repository, known['evidence_id']),
                                                    'reason': None, 'confidence': None, 'change': None}, 'receipts': [], 'error': None}
        recorder.finish('STORED', evidence_id=known['evidence_id'])
        return {'run_id': run_id, 'status': 'done', 'duplicate': True, 'provenance': 'live', 'workspace': state.workspace,
                'status_url': f'/api/runs/{run_id}', 'outcome': recorder.record['outcome']}

    state.uploads_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    recorder.emit('UPLOAD', 'RECEIVED', 'Screenshot received.', input_refs=[f'image:{path.name}'], next_step='EVIDENCE', detail=received)
    task = asyncio.create_task(_process(state, recorder, path, digest))
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    if wait:
        await task
        record = recorder.record
        if record['status'] == 'failed':
            code = 503 if record.get('error_kind') == 'gateway' else 502
            raise HTTPException(status_code=code, detail=record['result']['error'] or 'The screenshot could not be processed.')
        return {'run_id': run_id, 'status': record['status'], 'provenance': 'live', 'workspace': state.workspace, 'status_url': f'/api/runs/{run_id}',
                'outcome': record['outcome'], 'result': record['result']}
    return JSONResponse(status_code=202, content={'run_id': run_id, 'status': 'running', 'provenance': 'live', 'workspace': state.workspace,
                                                  'status_url': f'/api/runs/{run_id}'})
