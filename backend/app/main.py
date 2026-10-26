"""Small read-only HTTP composition layer. Agents and the visual frontend are unchanged."""
from contextlib import asynccontextmanager
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
from backend.app.bootstrap import open_repository, sample_mode
from backend.app.orchestration.consolidation import apply_merge, short

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
SCREENSHOTS = Path(os.environ.get('RECALL_SCREENSHOT_DIR') or Path(__file__).resolve().parents[2] / 'screenshot')
VIEW_TTL_SECONDS = 60
SUPPORTED_DOMAINS = {'food', 'shopping', 'travel'}
TIMEZONE = ZoneInfo(os.environ.get('RECALL_TIMEZONE', 'Australia/Melbourne'))
CHECK_IN_RESPONSES = {'same', 'different', 'related', 'other'}


@asynccontextmanager
async def lifespan(app):
    with open_repository() as repository:
        app.state.repository = repository
        app.state.mode = 'sample' if sample_mode() else 'real'
        app.state.sample = None
        if sample_mode():
            from backend.app.sample import run_sample
            app.state.sample = await run_sample(repository)
        else:
            # Warm the slow Zetaris reads so the first screen does not wait.
            Thread(target=lambda: (_cached('evidence', lambda: {e.evidence_id: e for e in repository.list_evidence()}),
                                   _cached('loops', lambda: _loop_views(repository)),
                                   _cached('zetaris', lambda: _zetaris_counts(repository))), daemon=True).start()
        yield


app = FastAPI(title='Recall data API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:5175', 'http://127.0.0.1:5175'], allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@app.exception_handler(ZetarisError)
async def storage_error(request, error):
    return JSONResponse(status_code=503, content={'detail': 'Recall storage is unavailable. No sample fallback was used.'})


@app.get('/health')
def health(request: Request):
    return {'status': 'ok', 'mode': request.app.state.mode, 'repository': type(request.app.state.repository).__name__,
            'external_models_used': False if request.app.state.mode == 'sample' else None}


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
    if request.app.state.mode == 'sample':
        items = sorted(repository.entities.values(), key=lambda item: item.entity_id)
        if domain is not None:
            items = [item for item in items if item.domain == domain]
    else:
        items = repository.list_entities(domain=domain)
    return [entity_view(repository, entity) for entity in items]


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


def _zetaris_counts(repository):
    return {'connected': True, 'evidence': len(repository.list_evidence()), 'entities': len(repository.list_entities()),
            'open_loops': len(repository.get_active_open_loops(limit=1000))}


def _evidence_by_entity(repository, entity_ids):
    """entity_id -> Evidence, in a constant number of queries on Zetaris."""
    by_entity = defaultdict(list)
    if hasattr(repository, 'list_evidence'):
        evidence = {item.evidence_id: item for item in repository.list_evidence()}
        for edge in repository.get_evidence_entities(list(evidence)):
            if edge.entity_id in entity_ids:
                by_entity[edge.entity_id].append(evidence[edge.evidence_id])
    else:
        for entity_id in entity_ids:
            by_entity[entity_id] = repository.get_related_evidence([entity_id], limit=1000)
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
    if hasattr(repository, 'list_evidence'):
        evidence = _cached('evidence', lambda: {e.evidence_id: e for e in repository.list_evidence()}).get(evidence_id)
    else:
        evidence = repository.get_evidence(evidence_id)
    # Sensitive Evidence never leaves the repository, and only a plain basename inside the screenshot folder is served.
    if evidence is None or evidence.sensitive or not evidence.image_ref or Path(evidence.image_ref).name != evidence.image_ref:
        raise HTTPException(status_code=404, detail='Image not found.')
    path = (SCREENSHOTS / evidence.image_ref).resolve()
    if path.parent != SCREENSHOTS.resolve() or not path.is_file():
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
    views = {v['loop_id']: v for v in _cached('loops', lambda: _loop_views(repository))} if request.app.state.mode == 'real' else {}
    base = str(request.base_url).rstrip('/')
    questions = []
    for item in repository.get_check_ins(day=_today(), status='PENDING'):
        if request.app.state.mode == 'real' and not all(i in views for i in (item.loop_id, item.other_loop_id) if i):
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
        raise HTTPException(status_code=404, detail='Sample fixtures are disabled in real mode.')
    return request.app.state.sample


def _read_report(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _saved_runs():
    """Real reasoning runs saved by backend/scripts (context_eval, process_open_loops). Read-only."""
    runs = {}
    folder = RUNTIME / 'context_eval'
    for path in sorted(folder.glob('context-eval-*.json')):
        for name, scenario in _read_report(path).get('scenarios', {}).items():
            result = scenario.get('result', {})
            if result.get('run_id'):
                runs[result['run_id']] = {'run_id': result['run_id'], 'kind': 'context_critic', 'scenario': name,
                                          'synthetic_context': bool(scenario.get('synthetic')), 'final_action': result.get('final_action'),
                                          'trace_events': result.get('trace_events', []), 'result': result, 'source_file': path.name,
                                          'context_event': scenario.get('context_event'), 'loop_title': _read_report(path).get('loop_title')}
    for path in sorted(folder.glob('revision-fixture-*.json')):
        report = _read_report(path)
        result = report.get('result', {})
        if result.get('run_id'):
            runs[result['run_id']] = {'run_id': result['run_id'], 'kind': 'revision_fixture', 'scenario': 'revision', 'synthetic_context': True,
                                      'final_action': result.get('final_action'), 'trace_events': result.get('trace_events', []),
                                      'result': result, 'source_file': path.name, 'original_title': report.get('original_title'),
                                      'final_title': report.get('final_title')}
    return runs


@app.get('/runs')
def runs(request: Request):
    """Latest saved real run per scenario, as full RunResult objects for Agent Activity. Inputs flagged synthetic are labelled."""
    if request.app.state.mode == 'sample':
        return []
    latest = {}
    for run in _saved_runs().values():
        if not any(event.get('agent') == 'ZETARIS' for event in run['trace_events']) and run['kind'] == 'context_critic':
            continue  # older runs saved before repository reads were traced
        key = run['scenario']
        if key not in latest or run['source_file'] > latest[key]['source_file']:
            latest[key] = run
    order = ['A_relevant', 'B_restraint', 'revision']
    return [{k: v for k, v in latest[key].items() if k != 'trace_events'} for key in order if key in latest]


@app.get('/integration-status')
def integration_status(request: Request):
    # Separate metadata, not invented TraceEvents or a forced visualization state.
    repository = request.app.state.repository
    proof = _read_report(RUNTIME / 'proofs/IMG_8922.roundtrip.json')
    run = _read_report(RUNTIME / 'proofs/IMG_8922.run.json')
    stored = repository.get_evidence(proof['evidence_id']) if request.app.state.mode == 'real' and proof.get('evidence_id') else None
    roundtrip = bool(stored and stored.source == 'screenshot' and proof.get('verified') and proof.get('kind') == 'real_zetaris_roundtrip')
    if roundtrip:
        loop = repository.get_open_loop(proof.get('loop_id', ''))
        edges = repository.get_loop_entities([proof.get('loop_id', '')])
        entity_ids = sorted({edge.entity_id for edge in edges})
        roundtrip = bool(loop and entity_ids and stored in repository.get_related_evidence(entity_ids, limit=10000))
    orchestrator = bool(roundtrip and run.get('verified') and run.get('kind') == 'real_zetaris_orchestrator_run' and run.get('evidence_id') == proof.get('evidence_id'))
    receipts = {label: {key: proof.get('receipts', {}).get(label, {}).get(key) for key in ('requested_model', 'routed_model', 'provider')}
                for label in ('perception', 'reasoning')} if roundtrip else {}
    zetaris = None
    if request.app.state.mode == 'real':
        # Live counts from the repository; no cached or invented values.
        zetaris = _cached('zetaris', lambda: _zetaris_counts(repository))
    return {'zetaris': zetaris, 'saved_reasoning_runs': [{k: v for k, v in r.items() if k != 'trace_events'} for r in _saved_runs().values()],
            'repository': type(repository).__name__, 'mode': request.app.state.mode,
            'real_roundtrip_verified': roundtrip, 'real_orchestrator_verified': orchestrator,
            'status': 'verified' if orchestrator else 'integration_pending',
            'receipts': receipts,
            'run_id': run.get('result', {}).get('run_id') if orchestrator else None}


@app.get('/agent-events/{run_id}')
def agent_events(request: Request, run_id: str):
    if request.app.state.mode == 'sample':
        result = request.app.state.sample['result']
    else:
        result = _read_report(RUNTIME / 'proofs/IMG_8922.run.json').get('result', {})
    if result.get('run_id') != run_id:
        saved = _saved_runs().get(run_id) if request.app.state.mode == 'real' else None
        if saved is None:
            raise HTTPException(status_code=404, detail='Run not found.')
        return saved['trace_events']
    return result.get('trace_events', [])
