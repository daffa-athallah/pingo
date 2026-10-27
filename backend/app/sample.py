"""Sample mode reads cached product history. It never manufactures or reruns decisions."""
from copy import deepcopy
import json
from pathlib import Path

from backend.app.bootstrap import sample_mode
from backend.app.repositories.context_store import Notification

HISTORY = Path(__file__).resolve().parents[1] / 'demo/history.json'


def read_history():
    data = json.loads(HISTORY.read_text())
    records = data['records']
    if not records or any(r.get('provenance') != 'recorded' or not r.get('cached') for r in records):
        raise ValueError('Sample history must contain explicitly cached run records.')
    return deepcopy(data)


def notification_for(repository, record, *, read=True, prefix='cached_', source='CACHED'):
    """The in-app notification for one stored SURFACE decision, in the existing notification contract, or None.

    `source` is CACHED so the browser never raises an OS notification for it: this is a view of a recorded decision, not delivery.
    An unread one appears in the in-app banner exactly like a live ping; a read one only opens from the recall detail page."""
    result = record['result']
    payload = result.get('message_payload') or {}
    loop = repository.get_open_loop(payload.get('loop_id'))
    evidence = [repository.get_evidence(i) for i in payload.get('evidence_ids', [])]
    if result.get('final_action') != 'SURFACE' or not loop or not evidence or any(e is None or e.sensitive for e in evidence):
        return None
    entities = repository.get_entities(sorted({k.entity_id for k in repository.get_loop_entities([loop.loop_id])}))
    event = record.get('context_event') or (record.get('context_events') or [{}])[0]
    return Notification(prefix + record['run_id'], loop.loop_id, record['started_at'], {
        'title': loop.title, 'message': 'An intention you saved may be relevant now. Revisit the evidence behind it.',
        'reason': payload['reason'], 'run_id': record['run_id'],
        'sources': [source, *(['SIMULATED'] if record.get('synthetic_inputs') else [])],
        'trigger_types': [event.get('context_type', 'CALENDAR')],
        'context_ids': payload.get('context_ids', []),
        'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in entities],
        'evidence': [{'evidence_id': e.evidence_id, 'summary': e.summary, 'image_url': f'/evidence/{e.evidence_id}/image' if e.image_ref else None} for e in evidence],
        'cached': True, 'original_delivery_verified': False,
        'delivery_status': 'APPROVED', 'read': read, 'dismissed': False, 'feedback': None,
        'snoozed_until': None, 'feedback_events': [],
    })


def cached_recall_views(repository, records):
    """Adapt stored SURFACE payloads to the existing recall-detail contract.

    These are views of historical decisions, not evidence of notification delivery. They start read so merely loading the app does not
    display a new notification. Feedback is handled by the existing service on this disposable local repository."""
    views = []
    for record in records:
        notice = notification_for(repository, record)
        if notice is None:
            continue
        payload = record['result']['message_payload']
        repository.save_notification(notice)
        views.append({'notification_id': notice.notification_id, 'loop_id': notice.loop_id, 'run_id': record['run_id'],
                      'title': notice.payload['title'], 'context': record.get('context_event'), 'reason': payload['reason'],
                      'evidence_ids': payload['evidence_ids'], 'captured_at': record['started_at'],
                      'synthetic_inputs': record.get('synthetic_inputs', False)})
    return views


async def run_sample(repository=None):
    if not sample_mode():
        raise RuntimeError('Set SAMPLE_MODE=true to read the cached history.')
    data = read_history()
    views = cached_recall_views(repository, data['records']) if repository is not None else []
    return {'mode': 'sample', 'data_source': 'cached_run_history', 'provenance': 'recorded',
            'workspace': 'sample', 'model_calls': False, 'agents_executed': False,
            'repository': 'InMemoryLoopRepository', 'cached_at': data['cached_at'],
            'records': data['records'], 'recall_views': views,
            'result': next((r['result'] for r in data['records'] if r['result']['final_action'] == 'SURFACE'), data['records'][0]['result'])}
