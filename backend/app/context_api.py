"""POST /api/context/evaluate: run Context -> Critic (and the bounded revision/verification branches) for events the client reports.

Intended for a phone UI (browser geolocation, a calendar demo). The evaluation is READ-ONLY with respect to stored data: any loop revision
the Critic asks for is visible in the trace but is never persisted. Model calls go Recall -> Nightshift -> Nemotron.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.bootstrap import build_orchestrator, sample_mode
from backend.app.context_policy import sensitive_reason
from backend.app.domain.models import ContextEvent, ContextType
from backend.app.orchestration.consolidation import short
from backend.app.orchestration.recall import FinalAction
from backend.app.repositories.overlay import ReadOnlyOverlayRepository

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


def _message(final_action: str, surface: dict | None, question: str | None) -> dict | None:
    """A ready-to-show notification text, built from the loop title and the Critic's own short reason. No extra model call."""
    if final_action == 'SURFACE' and surface:
        return {'kind': 'SURFACE', 'title': short(surface['loop'].get('title') or 'Saved intention'), 'body': surface['why_now']}
    if final_action == 'ASK' and question:
        return {'kind': 'ASK', 'title': 'A quick question', 'body': question}
    return None


async def _evaluate(request: Request, body: EvaluateRequest) -> dict:
    state = request.app.state
    provenance = 'scripted' if sample_mode() else 'live'
    kept, skipped, described = [], [], []
    for item in body.events:
        context_id = 'ctx_' + uuid.uuid4().hex[:10]
        reason = sensitive_reason(item.title, item.location_name)
        if reason:
            # The private title is not echoed back.
            skipped.append({'context_id': context_id, 'title': None, 'reason': reason})
            described.append({'context_id': context_id, 'context_type': item.context_type, 'evaluated': False, 'skipped_reason': reason})
            continue
        event = ContextEvent(context_id, ContextType(item.context_type), item.title.strip(), item.occurs_at, item.location_name, item.city, item.country)
        kept.append(event)
        described.append({'context_id': context_id, 'context_type': item.context_type, 'title': event.title, 'occurs_at': event.occurs_at,
                          'location_name': event.location_name, 'city': event.city, 'evaluated': True})
    common = {'provenance': provenance, 'workspace': state.workspace, 'synthetic': body.synthetic, 'events': described, 'skipped_events': skipped}
    if not kept:
        return {**common, 'run_id': None, 'status': 'done', 'decision': 'STAY_SILENT', 'final_action': 'STAY_SILENT', 'message': None,
                'surface': None, 'ask': None, 'error': None, 'result': None, 'receipts': []}
    repository = ReadOnlyOverlayRepository(state.repository)
    try:
        async with _gateway() as gateway:
            result = await build_orchestrator(gateway, repository).evaluate_context(kept)
    except ModelGatewayError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    run = result.to_dict()
    run['trace_events'] = [{**e, 'seq': i + 1, 'detail': None} for i, e in enumerate(run['trace_events'])]
    state.runs.save_finished({
        'run_id': result.run_id, 'kind': 'context_evaluate', 'label': 'Context evaluation', 'provenance': provenance, 'workspace': state.workspace,
        'synthetic_inputs': body.synthetic, 'status': 'failed' if result.final_action == FinalAction.FAILED_SAFE else 'done',
        'started_at': run['trace_events'][0]['timestamp'] if run['trace_events'] else None,
        'finished_at': run['trace_events'][-1]['timestamp'] if run['trace_events'] else None,
        'context_events': described, 'result': run})
    surface = _surface(result, repository, kept)
    return {**common, 'run_id': result.run_id, 'status': 'done', 'decision': result.final_action.value, 'final_action': result.final_action.value,
            'message': _message(result.final_action.value, surface, result.question),
            'surface': surface,
            'ask': ({'question': result.question, 'loop_id': result.loop_id} if result.final_action == FinalAction.ASK else None),
            'error': result.error,
            'receipts': [{'agent': e['agent'], 'action': e['action'], 'receipt': e['receipt']} for e in run['trace_events'] if e['receipt']],
            'result': run}


@router.post('/api/context/evaluate')
@router.post('/context/evaluate')
async def evaluate_context(request: Request, body: EvaluateRequest):
    """The one generic door for context. A UI, a demo script or a future calendar/location integration all send the same normalized events."""
    return await _evaluate(request, body)
