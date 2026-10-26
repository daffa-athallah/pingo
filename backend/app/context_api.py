"""POST /api/context/evaluate: run Context -> Critic (and the bounded revision/verification branches) for events the client reports.

Intended for a phone UI (browser geolocation, a calendar demo). The evaluation is READ-ONLY with respect to stored data: any loop revision
the Critic asks for is visible in the trace but is never persisted. Model calls go Recall -> Nightshift -> Nemotron.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.bootstrap import build_orchestrator, sample_mode
from backend.app.context_policy import sensitive_reason
from backend.app.domain.models import ContextEvent, ContextType
from backend.app.orchestration.recall import FinalAction
from backend.app.repositories.overlay import ReadOnlyOverlayRepository

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
LIVE_RUNS = RUNTIME / 'live_runs'
router = APIRouter()


class ContextEventIn(BaseModel):
    context_type: Literal['CALENDAR', 'LOCATION', 'TIME']
    title: str = Field(min_length=1, max_length=200)
    occurs_at: str | None = Field(default=None, max_length=64)
    location_name: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)


class EvaluateRequest(BaseModel):
    events: list[ContextEventIn] = Field(min_length=1, max_length=5)
    synthetic: bool = True  # label only: true when the events are demo/test input rather than real device data


@asynccontextmanager
async def _gateway():
    if sample_mode():
        from backend.app.sample import SampleGateway
        yield SampleGateway()  # scripted fixture; no model is called
        return
    async with ModelGateway.from_env() as gateway:
        yield gateway


def _surface(result, repository, events) -> dict | None:
    if result.final_action != FinalAction.SURFACE or not result.message_payload:
        return None
    payload = result.message_payload
    loop = repository.get_open_loop(payload['loop_id'])
    links = repository.get_loop_entities([payload['loop_id']])
    entities = repository.get_entities(sorted({k.entity_id for k in links}))
    evidence = []
    for evidence_id in payload.get('evidence_ids', []):
        reader = getattr(repository, 'get_evidence', None)
        item = reader(evidence_id) if reader else getattr(repository, 'evidence', {}).get(evidence_id)  # in-memory repository
        if item and not item.sensitive:
            evidence.append({'evidence_id': item.evidence_id, 'summary': item.summary, 'timestamp': item.timestamp,
                             'image_url': f'/evidence/{item.evidence_id}/image' if item.image_ref else None})
    cited = set(payload.get('context_ids', []))
    return {
        'loop': {'loop_id': loop.loop_id, 'title': loop.title, 'domain': loop.domain, 'status': loop.status.value,
                 'confidence': loop.confidence} if loop else {'loop_id': payload['loop_id'], 'title': payload.get('title')},
        'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in entities],
        'why_now': payload.get('reason'),
        'evidence': evidence,
        'context': [{'context_id': e.context_id, 'context_type': e.context_type.value, 'title': e.title, 'occurs_at': e.occurs_at,
                     'location_name': e.location_name, 'city': e.city} for e in events if e.context_id in cited],
    }


async def _evaluate(request: Request, body: EvaluateRequest) -> dict:
    kept, skipped = [], []
    for item in body.events:
        context_id = 'ctx_' + uuid.uuid4().hex[:10]
        reason = sensitive_reason(item.title, item.location_name)
        if reason:
            skipped.append({'context_id': context_id, 'title': None, 'reason': reason})  # the private title is not echoed back
            continue
        kept.append(ContextEvent(context_id, ContextType(item.context_type), item.title.strip(), item.occurs_at,
                                 item.location_name, item.city, item.country))
    if not kept:
        return {'run_id': None, 'final_action': 'STAY_SILENT', 'synthetic': body.synthetic, 'skipped_events': skipped, 'surface': None,
                'ask': None, 'result': None, 'receipts': []}
    repository = ReadOnlyOverlayRepository(request.app.state.repository)
    try:
        async with _gateway() as gateway:
            result = await build_orchestrator(gateway, repository).evaluate_context(kept)
    except ModelGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    LIVE_RUNS.mkdir(parents=True, exist_ok=True)
    saved = {'synthetic': body.synthetic, 'saved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'result': result.to_dict(),
             'context_events': [e.__dict__ | {'context_type': e.context_type.value} for e in kept]}
    (LIVE_RUNS / f'{result.run_id}.json').write_text(json.dumps(saved, indent=2, ensure_ascii=False))
    return {'run_id': result.run_id, 'final_action': result.final_action.value, 'synthetic': body.synthetic, 'skipped_events': skipped,
            'surface': _surface(result, repository, kept),
            'ask': ({'question': result.question, 'loop_id': result.loop_id} if result.final_action == FinalAction.ASK else None),
            'error': result.error,
            'receipts': [{'agent': e.agent, 'action': e.action, 'receipt': e.receipt} for e in result.trace_events if e.receipt],
            'result': result.to_dict()}


@router.post('/api/context/evaluate')
@router.post('/context/evaluate')
async def evaluate_context(request: Request, body: EvaluateRequest):
    return await _evaluate(request, body)


@router.get('/api/runs/{run_id}')
def live_run(run_id: str):
    path = (LIVE_RUNS / f'{run_id}.json').resolve()
    if path.parent != LIVE_RUNS.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail='Run not found.')
    return json.loads(path.read_text())
