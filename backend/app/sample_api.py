"""Sample mode: browse saved history, and replay a bundled example through the real agents.

Replay never calls a model. Unchanged agents run against replies captured earlier from Nightshift (see demo/recordings/README.md); a request that
differs from the recording fails closed. There is no free-form input here, so nothing can be answered with a canned reply."""
import json
from datetime import datetime
from pathlib import Path
from dataclasses import replace
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.app import tracelog
from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.demo_workspace import read_snapshot, seed
from backend.app.sample import notification_for
from backend.app.sample_cases import CASES, IMAGES, replay_case

router = APIRouter()
ZETARIS_PROOF = Path(__file__).resolve().parents[1] / 'demo/zetaris_proof.json'
INGEST = ('attach', 'create', 'sensitive')  # the cases that start from a saved screenshot
KIND = {'attach': 'screenshot', 'create': 'screenshot', 'sensitive': 'screenshot',
        'surface': 'location', 'restraint': 'location', 'revision': 'review', 'duplicates': 'review'}


def _sample_only(request: Request):
    if request.app.state.mode != 'sample':
        raise HTTPException(status_code=404, detail='Recorded examples are available only in sample mode.')


@router.get('/api/sample/history')
def history(request: Request):
    _sample_only(request)
    sample = request.app.state.sample
    return {k: sample[k] for k in ('cached_at', 'data_source', 'provenance', 'workspace', 'model_calls', 'agents_executed', 'records', 'recall_views')}


@router.get('/api/sample/zetaris')
def zetaris(request: Request):
    """A read-only capture of the real Zetaris instance (table counts and the agents' queries). Sample mode does not connect to Zetaris."""
    _sample_only(request)
    return json.loads(ZETARIS_PROOF.read_text())


@router.get('/api/sample/cases')
def cases(request: Request):
    _sample_only(request)
    return [{'case': case, 'label': label, 'kind': KIND[case], 'image_url': f'/api/sample/cases/{case}/image' if case in ('attach', 'create') else None,
             'sensitive': case == 'sensitive'} for case, label in CASES.items()]


TABLES = ('evidence', 'entities', 'loops')
LISTS = ('evidence_entities', 'loop_entities')


def _apply(state, case, result):
    """Show the replayed outcome in the product screens. The sample workspace becomes the saved history plus this one case
    (look-alike review adds its labelled synthetic loops instead), so every example starts from the same snapshot.
    Notifications and cached context history are left alone."""
    target = state.repository
    if case != 'duplicates':
        seed(target, read_snapshot())
    for name in TABLES:
        getattr(target, name).update(getattr(result, name))
    for name in LISTS:
        current = getattr(target, name)
        current.extend(item for item in getattr(result, name) if item not in current)
    today = datetime.now(ZoneInfo('Australia/Melbourne')).date().isoformat()
    target.check_ins.clear()
    target.check_ins.update({k: replace(v, day=today) for k, v in result.check_ins.items()})  # a Check-in belongs to one day: today
    state.on_data_changed()


def _clear_announcements(repository):
    for key in [k for k in repository.notifications if k.startswith('replay_')]:
        del repository.notifications[key]


def _announce(state, record):
    """A replayed SURFACE decision becomes an unread in-app notification (the banner), like a live ping. Never an OS notification."""
    repository = state.repository
    _clear_announcements(repository)
    notice = notification_for(repository, record, read=False, prefix='replay_')
    if notice is not None:
        notice = replace(notice, created_at=datetime.now(ZoneInfo('UTC')).isoformat(timespec='seconds'))  # a ping that just arrived, not the capture time
        repository.save_notification(notice)
        record['notification_id'] = notice.notification_id


@router.post('/api/sample/reset')
def reset(request: Request):
    _sample_only(request)
    seed(request.app.state.repository, read_snapshot())
    _clear_announcements(request.app.state.repository)
    request.app.state.on_data_changed()
    return {'ok': True}


@router.post('/api/sample/cases/{case}/replay')
async def replay(request: Request, case: str):
    _sample_only(request)
    if case not in CASES:
        raise HTTPException(status_code=404, detail='Unknown example.')
    captured = []
    try:
        record = await replay_case(case, capture=captured)
    except (ModelGatewayError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=f'The recording no longer matches its inputs ({exc}).') from None
    _apply(request.app.state, case, captured[0])
    _announce(request.app.state, record)
    request.app.state.runs.add_finished(record)
    return record


@router.get('/api/sample/cases/{case}/image')
def case_image(request: Request, case: str):
    _sample_only(request)
    path = IMAGES / f'{case}.png'
    if case not in ('attach', 'create') or not path.is_file():  # the sensitive test image is never served
        raise HTTPException(status_code=404, detail='No image for this example.')
    return FileResponse(path, media_type='image/png')
