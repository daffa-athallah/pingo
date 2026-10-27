"""Sample mode: browse saved history, and replay a bundled example through the real agents.

Replay never calls a model. Unchanged agents run against replies captured earlier from Nightshift (see demo/recordings/README.md); a request that
differs from the recording fails closed. There is no free-form input here, so nothing can be answered with a canned reply."""
import json
import os
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
        'surface': 'location', 'restraint': 'location', 'revision': 'review', 'duplicates': 'review', 'clarify': 'review'}
CLARIFY_LABEL = 'Uncertain save → Pingo asks you (labelled fixture)'


def _sample_only(request: Request):
    if request.app.state.mode != 'sample':
        raise HTTPException(status_code=404, detail='Recorded examples are available only in sample mode.')


@router.get('/api/sample/history')
def history(request: Request):
    _sample_only(request)
    sample = request.app.state.sample
    return {k: sample[k] for k in ('cached_at', 'data_source', 'provenance', 'workspace', 'model_calls', 'agents_executed', 'records', 'recall_views')}


@router.get('/api/sample/phone-link')
def phone_link(request: Request):
    """The address a phone on the same Wi-Fi should open, if the person who started the server supplied one (RECALL_PUBLIC_URL). Never guessed."""
    _sample_only(request)
    url = os.environ.get('RECALL_PUBLIC_URL', '').strip()
    return {'url': url if url.startswith(('http://', 'https://')) and len(url) < 200 else None}


@router.get('/api/sample/zetaris')
def zetaris(request: Request):
    """A read-only capture of the real Zetaris instance (table counts and the agents' queries). Sample mode does not connect to Zetaris."""
    _sample_only(request)
    return json.loads(ZETARIS_PROOF.read_text())


@router.get('/api/sample/cases')
def cases(request: Request):
    _sample_only(request)
    return [{'case': case, 'label': label, 'kind': KIND[case], 'image_url': f'/api/sample/cases/{case}/image' if case in ('attach', 'create') else None,
             'sensitive': case == 'sensitive'} for case, label in {**CASES, 'clarify': CLARIFY_LABEL}.items()]


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
    if case == 'clarify':
        return _clarify(request)
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


def _clarify(request: Request):
    """A labelled fixture of the Open Loop Agent reporting material uncertainty. It runs no model: the question is written here, grounded in a
    saved screenshot of the sample history, and queued through the same Check-in code the live app uses. Answering it saves the answer only."""
    from backend.app.checkin_clarifications import KIND as CHECK_IN_KIND, queue
    from backend.app.runs import RunStore
    state = request.app.state
    repository = state.repository
    seed(repository, read_snapshot())
    _clear_announcements(repository)
    repository.check_ins.clear()
    link = next((l for l in repository.evidence_entities
                 if (e := repository.get_evidence(l.evidence_id)) and e.image_ref and not e.sensitive and e.domain == 'food'
                 and not any(w in e.summary.lower() for w in ('order', 'receipt', 'confirmation', 'booking'))
                 and any(x.entity_type == 'place' for x in repository.get_entities([l.entity_id]))), None)
    if link is None:
        raise HTTPException(409, 'The sample history has no screenshot to ask about.')
    evidence, entity = repository.get_evidence(link.evidence_id), repository.get_entities([link.entity_id])[0]
    uncertainty = f'The screenshot of {entity.name} does not say whether you plan to go or only wanted to remember it.'
    qid = queue(repository, [evidence], [entity], text=f'Is {entity.name} somewhere you want to go, or just something you wanted to remember?',
                options=[{'value': 'go', 'label': 'I want to go'}, {'value': 'remember', 'label': 'Just remembering it'}],
                uncertainty=uncertainty, origin='OPEN_LOOP', loop_id=None, model_receipt=None, run_id='run_sample_clarify')
    recorder = RunStore('sample').start('run_sample_clarify', kind='recorded_sample', provenance='recorded', run_type='EVIDENCE_INGESTION',
                                        label=CLARIFY_LABEL, synthetic_inputs=True)
    recorder.emit('EVIDENCE', 'EXTRACT', f'Read the saved screenshot of {entity.name}.', next_step='OPEN_LOOP')
    recorder.emit('OPEN_LOOP', 'LEAVE_UNRESOLVED', uncertainty, next_step='CHECK_IN')
    recorder.emit('OPEN_LOOP', 'ASK', 'A material uncertainty needs your answer, so Pingo asks instead of guessing.', output_ref=f'checkin:{qid}', next_step='CHECK_IN')
    recorder.emit('CHECK_IN', 'WAITING', 'One question is waiting in Check-in. Your answer is what the Open Loop Agent reads next.', next_step='OUTPUT')
    record = recorder.finish('ASK')
    record['check_ins'] = [{'question': repository.get_check_in(qid).question['question']}] if qid else []
    record['recording_note'] = 'Labelled fixture: the uncertainty and question are written for this example. No live model or memory engine was called.'
    state.on_data_changed()
    state.runs.add_finished(record)
    return record
