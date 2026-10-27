"""Context evaluation is an explicit POST. Notification GETs never invoke agents."""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request

from backend.app.context.contracts import EvaluationInput, NotificationAction
from backend.app.context.service import ContextConflict, ContextService

router = APIRouter()


@router.get('/context-simulator/places')
def context_places(request: Request):
    """Single repository read for verified-location inputs, without per-entity count/loop queries.

    These are stored coordinates, not geocoding or claims of current eligibility.
    The frontend separately requires active loop/evidence links before enabling presets.
    """
    keys = {'latitude', 'longitude', 'location_verified', 'location_source', 'location_role', 'store_name'}
    return [{'entity_id': entity.entity_id, 'name': entity.name, 'domain': entity.domain,
             'metadata': {key: value for key, value in entity.metadata.items() if key in keys}}
            for entity in request.app.state.repository.list_entities()
            if entity.domain in {'food', 'travel', 'shopping'}]


def service(request):
    from backend.app.intentions_api import HiddenEvidenceRepository, read_hidden
    state = request.app.state
    repo = state.repository
    current = getattr(state, 'context_service', None)
    if current is None or getattr(current, 'source_repository', getattr(current, 'repository', None)) is not repo:  # an injected service (tests) keeps its own repository
        current = ContextService(HiddenEvidenceRepository(repo, lambda: read_hidden(state)))  # deleted screenshots are not read back into reminders
        current.source_repository = repo
        state.context_service = current
    return current


@router.post('/context-simulator/evaluate')
async def evaluate_context(body: EvaluationInput, request: Request):
    if request.app.state.mode == 'sample':
        raise HTTPException(409, 'Context Simulator requires real repository/model configuration. SAMPLE_MODE fixtures are not real agent decisions.')
    try:
        return await service(request).evaluate(body)
    except ContextConflict as exc:
        raise HTTPException(409, str(exc)) from None


@router.get('/context/evaluations/{evaluation_id}')
def context_evaluation(evaluation_id: str, request: Request):
    record = request.app.state.repository.get_context_evaluation(evaluation_id)
    if record is None:
        raise HTTPException(404, 'Context evaluation not found.')
    return record.payload


@router.get('/notifications')
def notifications(request: Request):
    return service(request).list_notifications()


@router.get('/notifications/{notification_id}')
def notification(notification_id: str, request: Request):
    record = request.app.state.repository.get_notification(notification_id)
    if record is None or not service(request).visible(record):
        raise HTTPException(404, 'Notification is unavailable or no longer active.')
    return asdict(record)


@router.post('/notifications/{notification_id}/actions')
async def notification_action(notification_id: str, body: NotificationAction, request: Request):
    try:
        result = await service(request).action(notification_id, body.action)
        if body.action in {'DONE', 'SNOOZE', 'NOT_RELEVANT', 'JUST_INSPIRATION'}:
            # Existing Home reads must see the resolved state after explicit feedback.
            from backend.app.main import _view_cache, _view_lock
            with _view_lock:
                _view_cache.pop('loops', None)
        return result
    except KeyError:
        raise HTTPException(404, 'Notification not found.') from None
    except ContextConflict as exc:
        raise HTTPException(409, str(exc)) from None
