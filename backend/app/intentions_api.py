"""Delete an intention: hide it from Pingo and stop its reminders, without pretending the stored Evidence can be erased.

Open Loops are state, so a deleted one is marked INVALIDATED (the Open Loop Agent and every view already ignore those). Evidence in Zetaris is append-only and
is never edited or removed; the screenshots that belonged only to this intention are instead listed in a small local "hidden" file that the app's views honour.
The same images can then be synced again and processed from scratch."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.app.bootstrap import live_models
from backend.app.domain.models import LoopStatus

router = APIRouter()


def hidden_path(state) -> Path:
    return state.uploads_dir.parent / 'hidden_evidence.json'


def read_hidden(state) -> set[str]:
    try:
        return set(json.loads(hidden_path(state).read_text()))
    except (OSError, ValueError):
        return set()


def write_hidden(state, ids: set[str]) -> None:
    path = hidden_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(sorted(ids)))
    temporary.replace(path)


@router.post('/api/open-loops/{loop_id}/delete')
async def delete_intention(request: Request, loop_id: str):
    state = request.app.state
    if state.mode == 'sample' and not live_models():
        raise HTTPException(status_code=404, detail='Deleting is available on the real backend and the demo workspace.')
    repository = state.repository
    async with state.write_lock:
        loop = repository.get_open_loop(loop_id)
        if loop is None or loop.status == LoopStatus.INVALIDATED:
            raise HTTPException(status_code=404, detail='Intention not found.')
        mine = {k.entity_id for k in repository.get_loop_entities([loop_id])}
        others = {k.entity_id for l in repository.get_active_open_loops(limit=10000) if l.loop_id != loop_id for k in repository.get_loop_entities([l.loop_id])}
        exclusive = mine - others  # an entity shared with another intention keeps its screenshots
        links = repository.get_evidence_entities([e.evidence_id for e in repository.list_evidence()])
        evidence_ids = {k.evidence_id for k in links if k.entity_id in exclusive}
        repository.update_open_loop(loop_id, status=LoopStatus.INVALIDATED)
        write_hidden(state, read_hidden(state) | evidence_ids)
        # Let the same images be synced again: forget their duplicate fingerprints.
        index_path = state.uploads_dir / 'index.json'
        freed = 0
        try:
            index = json.loads(index_path.read_text())
            keep = {digest: row for digest, row in index.items() if row.get('evidence_id') not in evidence_ids}
            freed = len(index) - len(keep)
            if freed:
                temporary = index_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(keep, indent=2, sort_keys=True))
                temporary.replace(index_path)
        except (OSError, ValueError):
            pass
        if hasattr(state, 'on_data_changed'):
            state.on_data_changed()
    return {'deleted': loop_id, 'title': loop.title, 'screenshots_hidden': len(evidence_ids), 'can_sync_again': freed}


@router.post('/api/evidence/{evidence_id}/delete')
async def delete_screenshot(request: Request, evidence_id: str):
    """Hide one screenshot (see the module note: Evidence itself is append-only and stays stored) and allow the same image to be synced again."""
    state = request.app.state
    if state.mode == 'sample' and not live_models():
        raise HTTPException(status_code=404, detail='Deleting is available on the real backend and the demo workspace.')
    async with state.write_lock:
        if state.repository.get_evidence(evidence_id) is None:
            raise HTTPException(status_code=404, detail='Screenshot not found.')
        write_hidden(state, read_hidden(state) | {evidence_id})
        index_path = state.uploads_dir / 'index.json'
        freed = 0
        try:
            index = json.loads(index_path.read_text())
            keep = {digest: row for digest, row in index.items() if row.get('evidence_id') != evidence_id}
            freed = len(index) - len(keep)
            if freed:
                temporary = index_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(keep, indent=2, sort_keys=True))
                temporary.replace(index_path)
        except (OSError, ValueError):
            pass
        if hasattr(state, 'on_data_changed'):
            state.on_data_changed()
    return {'hidden': evidence_id, 'can_sync_again': freed}
