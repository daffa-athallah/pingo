"""Context evaluation is an explicit POST. Notification GETs never invoke agents."""
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request

from backend.app.context.contracts import EvaluationInput, NotificationAction
from backend.app.context.service import ContextConflict, ContextService

router = APIRouter()


def service(request):
    repo = request.app.state.repository
    current = getattr(request.app.state, 'context_service', None)
    if current is None or current.repository is not repo:
        current = ContextService(repo)
        request.app.state.context_service = current
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
        if body.action == 'DONE':
            # Existing Home reads must see the resolved state after explicit feedback.
            from backend.app.main import _view_cache, _view_lock
            with _view_lock:
                _view_cache.pop('loops', None)
        return result
    except KeyError:
        raise HTTPException(404, 'Notification not found.') from None
    except ContextConflict as exc:
        raise HTTPException(409, str(exc)) from None
