"""Small read-only HTTP composition layer. Agents and the visual frontend are unchanged."""
from contextlib import asynccontextmanager
import asyncio
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock, Thread
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

from backend.app.adapters.zetaris import ZetarisError
from backend.app.bootstrap import app_mode, open_repository
from backend.app.context_api import router as context_router
from backend.app.demo_workspace import SnapshotError, read_snapshot, seed, workspace_info
from backend.app.orchestration.consolidation import apply_merge, short
from backend.app.runs import RunStore, summary
from backend.app.runs_api import router as runs_router, workspace_runs
from backend.app.upload_api import router as upload_router

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
SCREENSHOTS = Path(os.environ.get('RECALL_SCREENSHOT_DIR') or Path(__file__).resolve().parents[2] / 'screenshot')
VIEW_TTL_SECONDS = 60
SUPPORTED_DOMAINS = {'food', 'shopping', 'travel'}
TIMEZONE = ZoneInfo(os.environ.get('RECALL_TIMEZONE', 'Australia/Melbourne'))
CHECK_IN_RESPONSES = {'same', 'different', 'related', 'other'}


def _paths(mode: str) -> tuple[Path, Path]:
    """(uploads, saved runs). The demo workspace keeps its own folders so it can never mix with canonical data."""
    base = RUNTIME if mode == 'real' else RUNTIME / 'demo'
    return base / 'uploads', base / 'live_runs'


@asynccontextmanager
async def lifespan(app):
    mode = app_mode()
    _view_cache.clear()
    with open_repository() as repository:
        uploads, run_dir = _paths(mode)
        app.state.repository = repository
        app.state.mode = mode
        app.state.workspace = {'real': 'canonical', 'demo': 'demo', 'sample': 'sample'}[mode]
        app.state.uploads_dir = uploads
        app.state.image_dirs = [] if mode == 'sample' else [SCREENSHOTS, uploads]
        app.state.runs = RunStore(app.state.workspace, None if mode == 'sample' else run_dir)
        app.state.write_lock = asyncio.Lock()  # Zetaris is safe with one writer: uploads are processed one at a time
        app.state.tasks = set()  # background upload runs, kept referenced until they finish
        app.state.on_data_changed = lambda: _refresh_views(repository)
        app.state.sample = None
        app.state.demo_info = workspace_info() if mode == 'demo' else None
        if mode == 'sample':
            from backend.app.sample import run_sample
            app.state.sample = await run_sample(repository)
            scripted = app.state.sample['result']
            app.state.runs.add_finished({'run_id': scripted['run_id'], 'kind': 'scripted_sample', 'label': 'Scripted sample', 'provenance': 'scripted',
                                         'workspace': 'sample', 'synthetic_inputs': True, 'status': 'done', 'started_at': None,
                                         'finished_at': None, 'result': scripted})
        else:
            # Warm the slow reads (Zetaris) so the first screen does not wait. Instant for the in-memory demo workspace.
            Thread(target=lambda: (_cached('evidence', lambda: {e.evidence_id: e for e in repository.list_evidence()}),
                                   _cached('loops', lambda: _loop_views(repository)),
                                   _cached('zetaris', lambda: _zetaris_counts(repository))), daemon=True).start()
        yield


app = FastAPI(title='Recall data API', lifespan=lifespan)
# Extra origins (for example a Tailscale HTTPS URL) come from the environment, never from code:
#   RECALL_CORS_ORIGINS=https://my-mac.tailnet.ts.net,https://ica-mac.tailnet.ts.net:5173
#   RECALL_CORS_ORIGIN_REGEX=https://.*\\.ts\\.net(:\\d+)?   (optional)
_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:5175', 'http://127.0.0.1:5175',
            *[o.strip().rstrip('/') for o in os.environ.get('RECALL_CORS_ORIGINS', '').split(',') if o.strip()]]
app.add_middleware(CORSMiddleware, allow_origins=_ORIGINS, allow_origin_regex=os.environ.get('RECALL_CORS_ORIGIN_REGEX') or None,
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.include_router(context_router)
app.include_router(upload_router)
app.include_router(runs_router)


@app.exception_handler(ZetarisError)
async def storage_error(request, error):
    return JSONResponse(status_code=503, content={'detail': 'Recall storage is unavailable. No sample fallback was used.'})


@app.get('/health')
def health(request: Request):
    state = request.app.state
    return {'status': 'ok', 'mode': state.mode, 'workspace': state.workspace, 'repository': type(state.repository).__name__,
            'external_models_used': False if state.mode == 'sample' else None,
            **({'demo_workspace': state.demo_info} if state.demo_info else {})}


def entity_view(repository, entity):
    evidence = repository.get_related_evidence([entity.entity_id], limit=10000)
    screenshots = [item for item in evidence if item.source == 'screenshot' and item.image_ref]
    loops = repository.get_candidate_open_loops([entity.entity_id], limit=1000)
    linked = {edge.loop_id for edge in repository.get_loop_entities([loop.loop_id for loop in loops]) if edge.entity_id == entity.entity_id}
    intentions = [loop for loop in loops if loop.loop_id in linked]
    return {**asdict(entity), 'id': entity.entity_id, 'location': entity.location_name or entity.city,
            'screenshot_count': len({item.evidence_id for item in screenshots}),
            'thumbnail_ref': next((item.image_ref for item in screenshots if not item.sensitive), None),
            'inferred_intention': intentions[0].title if intentions else None}


@app.get('/entities')
def entities(request: Request, domain: str | None = None):
    repository = request.app.state.repository
    return [entity_view(repository, entity) for entity in repository.list_entities(domain=domain)]


@app.get('/entities/{entity_id}')
def entity(request: Request, entity_id: str):
    repository = request.app.state.repository
    values = repository.get_entities([entity_id])
    if not values:
        raise HTTPException(status_code=404, detail='Entity not found.')
    return entity_view(repository, values[0])


@app.get('/loops')
def loops(request: Request):
    return [asdict(loop) for loop in request.app.state.repository.get_active_open_loops(limit=1000)]


_view_cache: dict = {}
_view_lock = Lock()
_building: set = set()


def _cached(key, build):
    """Zetaris JDBC round-trips are slow (seconds). Serve the last read immediately and refresh it in the background.
    Reads only; this is never a substitute for storage, and the first caller waits for a real read."""
    with _view_lock:
        hit = _view_cache.get(key)
    if hit is None:
        value = build()
        with _view_lock:
            _view_cache[key] = (time.monotonic(), value)
        return value
    if time.monotonic() - hit[0] >= VIEW_TTL_SECONDS:
        with _view_lock:
            start = key not in _building
            _building.add(key)
        if start:
            def refresh():
                try:
                    value = build()
                    with _view_lock:
                        _view_cache[key] = (time.monotonic(), value)
                except Exception:  # noqa: BLE001 - keep serving the previous read
                    pass
                finally:
                    with _view_lock:
                        _building.discard(key)
            Thread(target=refresh, daemon=True).start()
    return hit[1]


def _refresh_views(repository):
    """Stored data changed (an upload): drop the cached reads and rebuild them in the background."""
    with _view_lock:
        for key in ('loops', 'evidence', 'zetaris'):
            _view_cache.pop(key, None)
    Thread(target=lambda: (_cached('evidence', lambda: {e.evidence_id: e for e in repository.list_evidence()}),
                           _cached('loops', lambda: _loop_views(repository))), daemon=True).start()


def _zetaris_counts(repository):
    return {'connected': True, 'evidence': len(repository.list_evidence()), 'entities': len(repository.list_entities()),
            'open_loops': len(repository.get_active_open_loops(limit=1000))}


def _evidence_by_entity(repository, entity_ids):
    """entity_id -> Evidence, in a constant number of queries on Zetaris."""
    by_entity = defaultdict(list)
    evidence = {item.evidence_id: item for item in repository.list_evidence()}
    for edge in repository.get_evidence_entities(list(evidence)):
        if edge.entity_id in entity_ids:
            by_entity[edge.entity_id].append(evidence[edge.evidence_id])
    return by_entity


def _loop_views(repository):
    loops = [loop for loop in repository.get_active_open_loops(limit=1000) if loop.domain in SUPPORTED_DOMAINS]
    links = repository.get_loop_entities([loop.loop_id for loop in loops])
    entities = {item.entity_id: item for item in repository.get_entities(sorted({link.entity_id for link in links}))}
    by_entity = _evidence_by_entity(repository, set(entities))
    views = []
    for loop in loops:
        loop_entities = [entities[link.entity_id] for link in links if link.loop_id == loop.loop_id and link.entity_id in entities]
        seen, evidence = set(), []
        for item in sorted((e for entity in loop_entities for e in by_entity[entity.entity_id]), key=lambda e: (e.timestamp, e.evidence_id), reverse=True):
            if item.evidence_id not in seen:
                seen.add(item.evidence_id)
                evidence.append(item)
        # Sensitive Evidence is counted nowhere visible: no image, no summary, no ID.
        shown = [e for e in evidence if not e.sensitive]
        place = next((e for e in loop_entities if e.location_name or e.city), None)
        views.append({
            'loop_id': loop.loop_id, 'title': loop.title, 'domain': loop.domain, 'status': loop.status.value,
            'confidence': loop.confidence, 'updated_at': loop.updated_at,
            'location': (place.location_name or place.city) if place else None,
            'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in loop_entities],
            'screenshot_count': sum(1 for e in shown if e.image_ref),
            'screenshots': [{'evidence_id': e.evidence_id, 'summary': e.summary, 'timestamp': e.timestamp,
                             'image_url': f'/evidence/{e.evidence_id}/image'} for e in shown if e.image_ref],
        })
    views.sort(key=lambda v: (v['updated_at'], v['loop_id']), reverse=True)
    return views


@app.get('/open-loops')
def open_loops(request: Request, domain: str | None = None):
    """Open Loops with their linked entities and supporting screenshots (images served by /evidence/{id}/image)."""
    repository = request.app.state.repository
    views = _cached('loops', lambda: _loop_views(repository))
    return [v for v in views if domain is None or v['domain'] == domain]


@app.get('/open-loops/{loop_id}')
def open_loop(request: Request, loop_id: str):
    repository = request.app.state.repository
    for view in _cached('loops', lambda: _loop_views(repository)):
        if view['loop_id'] == loop_id:
            return view
    raise HTTPException(status_code=404, detail='Open loop not found.')


THUMBS = RUNTIME / 'thumbs'


def _thumbnail(source: Path, evidence_id: str, width: int) -> Path:
    """Phone screenshots can be megabytes; serve a cached JPEG scaled to `width`. Originals are never modified."""
    target = THUMBS / f'{evidence_id}-{width}.jpg'
    if not target.is_file():
        from PIL import Image, ImageOps
        THUMBS.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((width, width * 4))
            temporary = target.with_suffix('.tmp')
            image.save(temporary, 'JPEG', quality=82, optimize=True)
            temporary.replace(target)
    return target


@app.get('/evidence/{evidence_id}/image')
def evidence_image(request: Request, evidence_id: str, w: int = 800):
    repository = request.app.state.repository
    evidence = _cached('evidence', lambda: {e.evidence_id: e for e in repository.list_evidence()}).get(evidence_id)
    # Sensitive Evidence never leaves the repository, and only a plain basename inside the screenshot folder is served.
    if evidence is None or evidence.sensitive or not evidence.image_ref or Path(evidence.image_ref).name != evidence.image_ref:
        raise HTTPException(status_code=404, detail='Image not found.')
    # The imported screenshots live in SCREENSHOTS, this workspace's uploads in its own folder; only a plain basename inside one is served.
    path = next((candidate for folder in request.app.state.image_dirs if (candidate := (folder / evidence.image_ref).resolve()).parent == folder.resolve()
                 and candidate.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail='Image not found.')
    try:
        path = _thumbnail(path, evidence.evidence_id, min(max(w, 128), 1600))
    except Exception:  # noqa: BLE001 - unreadable image
        raise HTTPException(status_code=404, detail='Image not found.') from None
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'public, max-age=3600'})


def _today() -> str:
    return datetime.now(TIMEZONE).date().isoformat()


@app.get('/api/check-ins')
@app.get('/check-ins')
def check_ins(request: Request):
    """Today's unanswered questions only: a question belongs to one day and does not carry over, so Check-in refreshes daily."""
    repository = request.app.state.repository
    if not hasattr(repository, 'get_check_ins'):
        return {'questions': []}
    views = {v['loop_id']: v for v in _cached('loops', lambda: _loop_views(repository))} if request.app.state.mode != 'sample' else {}
    base = str(request.base_url).rstrip('/')
    questions = []
    for item in repository.get_check_ins(day=_today(), status='PENDING'):
        if request.app.state.mode != 'sample' and not all(i in views for i in (item.loop_id, item.other_loop_id) if i):
            continue  # a loop was merged or retired since the question was made
        question = dict(item.question)
        question['supporting_images'] = [
            {'url': f"{base}{views[i]['screenshots'][0]['image_url']}?w=600", 'alt': short(views[i]['title'])}
            for i in (item.loop_id, item.other_loop_id) if i in views and views[i]['screenshots']]
        questions.append(question)
    return {'questions': questions}


class CheckInAnswer(BaseModel):
    response: str
    comment: str | None = Field(default=None, max_length=500)


@app.post('/api/check-ins/{check_in_id}/respond')
@app.post('/check-ins/{check_in_id}/respond')
def respond_to_check_in(request: Request, check_in_id: str, answer: CheckInAnswer):
    """The person's answer settles the question. Only 'same' changes anything: it merges the two loops."""
    repository = request.app.state.repository
    item = repository.get_check_in(check_in_id) if hasattr(repository, 'get_check_in') else None
    if item is None:
        raise HTTPException(status_code=404, detail='Check-in not found.')
    if answer.response not in CHECK_IN_RESPONSES:
        raise HTTPException(status_code=422, detail='Unknown response.')
    if item.status == 'ANSWERED':
        if item.response == answer.response:
            return {'ok': True}
        raise HTTPException(status_code=409, detail='Check-in was already answered.')
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    if answer.response == 'same' and item.kind == 'MERGE_LOOPS' and item.other_loop_id:
        apply_merge(repository, item.loop_id, item.other_loop_id, now)
    repository.save_check_in(replace(item, status='ANSWERED', response=answer.response, comment=(answer.comment or '').strip() or None, answered_at=now))
    with _view_lock:
        _view_cache.pop('loops', None)
    return {'ok': True}


@app.get('/sample')
def sample(request: Request):
    if request.app.state.mode != 'sample':
        raise HTTPException(status_code=404, detail='The scripted sample fixture exists only in SAMPLE_MODE.')
    return request.app.state.sample


def _read_report(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


@app.get('/integration-status')
def integration_status(request: Request):
    # Separate metadata, not invented TraceEvents or a forced visualization state.
    state = request.app.state
    repository = state.repository
    real = state.mode == 'real'
    proof = _read_report(RUNTIME / 'proofs/IMG_8922.roundtrip.json') if real else {}
    run = _read_report(RUNTIME / 'proofs/IMG_8922.run.json') if real else {}
    stored = repository.get_evidence(proof['evidence_id']) if real and proof.get('evidence_id') else None
    roundtrip = bool(stored and stored.source == 'screenshot' and proof.get('verified') and proof.get('kind') == 'real_zetaris_roundtrip')
    if roundtrip:
        loop = repository.get_open_loop(proof.get('loop_id', ''))
        edges = repository.get_loop_entities([proof.get('loop_id', '')])
        entity_ids = sorted({edge.entity_id for edge in edges})
        roundtrip = bool(loop and entity_ids and stored in repository.get_related_evidence(entity_ids, limit=10000))
    orchestrator = bool(roundtrip and run.get('verified') and run.get('kind') == 'real_zetaris_orchestrator_run' and run.get('evidence_id') == proof.get('evidence_id'))
    receipts = {label: {key: proof.get('receipts', {}).get(label, {}).get(key) for key in ('requested_model', 'routed_model', 'provider')}
                for label in ('perception', 'reasoning')} if roundtrip else {}
    # Live counts from Zetaris, only when this really is Zetaris. The demo workspace is in-memory and says so.
    zetaris = _cached('zetaris', lambda: _zetaris_counts(repository)) if real else None
    return {'zetaris': zetaris, 'workspace': state.workspace, 'demo_workspace': state.demo_info,
            # Runs of THIS workspace only; another mode's runs are never listed here.
            'saved_reasoning_runs': [summary(r, include_events=False) for r in workspace_runs(request)],
            'repository': type(repository).__name__, 'mode': state.mode,
            'real_roundtrip_verified': roundtrip, 'real_orchestrator_verified': orchestrator,
            'status': 'verified' if orchestrator else 'integration_pending',
            'receipts': receipts,
            'run_id': run.get('result', {}).get('run_id') if orchestrator else None}


@app.post('/api/demo/reset')
async def reset_demo_workspace(request: Request):
    """Demo workspace only: restore the snapshot, forget this workspace's runs and uploads. Canonical data is never touched."""
    state = request.app.state
    if state.mode != 'demo':
        raise HTTPException(status_code=404, detail='There is no resettable demo workspace in this mode.')
    async with state.write_lock:  # waits for a run in progress instead of cutting it off
        try:
            seed(state.repository, read_snapshot())
        except SnapshotError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from None
        state.runs.clear()
        if state.uploads_dir.is_dir():
            for path in state.uploads_dir.iterdir():
                if path.is_file():
                    path.unlink(missing_ok=True)
        _refresh_views(state.repository)
    return {'ok': True, 'demo_workspace': workspace_info(), 'evidence': len(state.repository.list_evidence()),
            'active_loops': len(state.repository.get_active_open_loops(limit=1000))}
