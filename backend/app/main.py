"""Small read-only HTTP composition layer. Agents and the visual frontend are unchanged."""
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.adapters.zetaris import ZetarisError
from backend.app.bootstrap import open_repository, sample_mode

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'


@asynccontextmanager
async def lifespan(app):
    with open_repository() as repository:
        app.state.repository = repository
        app.state.mode = 'sample' if sample_mode() else 'real'
        app.state.sample = None
        if sample_mode():
            from backend.app.sample import run_sample
            app.state.sample = await run_sample(repository)
        yield


app = FastAPI(title='Recall data API', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['GET'])


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
    for path in sorted((RUNTIME / 'context_eval').glob('context-eval-*.json')):
        for name, scenario in _read_report(path).get('scenarios', {}).items():
            result = scenario.get('result', {})
            if result.get('run_id'):
                runs[result['run_id']] = {'run_id': result['run_id'], 'kind': 'context_critic', 'scenario': name,
                                          'synthetic_context': bool(scenario.get('synthetic')), 'final_action': result.get('final_action'),
                                          'trace_events': result.get('trace_events', [])}
    return runs


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
        zetaris = {'connected': True, 'evidence': len(repository.list_evidence()), 'entities': len(repository.list_entities()),
                   'open_loops': len(repository.get_active_open_loops(limit=1000))}
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
