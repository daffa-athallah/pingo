"""Delete an intention together with all of its screenshots.

Open Loops are state, so a deleted one is marked INVALIDATED (the Open Loop Agent and every view already ignore those). Evidence rows in Zetaris are append-only
and cannot be edited or removed, so each of the intention's screenshots is listed in a small local "hidden" file that every view honours, and the image files
that were uploaded through Pingo (and their thumbnails) are erased from this computer. The same images can then be synced again and processed from scratch."""
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


def erase_images(state, repository, evidence_ids) -> int:
    """Delete the uploaded image files (never the imported originals) and cached thumbnails of these screenshots. Returns how many files went."""
    from backend.app.main import THUMBS
    removed = 0
    uploads = state.uploads_dir.resolve()
    for evidence_id in evidence_ids:
        evidence = repository.get_evidence(evidence_id)
        ref = getattr(evidence, 'image_ref', None)
        if ref and Path(ref).name == ref:
            path = (state.uploads_dir / ref).resolve()
            if path.parent == uploads and path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        for thumb in THUMBS.glob(f'{evidence_id}-*.jpg'):
            thumb.unlink(missing_ok=True)
    return removed


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
        links = repository.get_evidence_entities([e.evidence_id for e in repository.list_evidence()])
        evidence_ids = {k.evidence_id for k in links if k.entity_id in mine}  # every screenshot this intention shows
        repository.update_open_loop(loop_id, status=LoopStatus.INVALIDATED)
        write_hidden(state, read_hidden(state) | evidence_ids)
        erased = erase_images(state, repository, evidence_ids)
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
    return {'deleted': loop_id, 'title': loop.title, 'screenshots_deleted': len(evidence_ids), 'image_files_erased': erased, 'can_sync_again': freed}


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
        erased = erase_images(state, state.repository, {evidence_id})
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
    return {'hidden': evidence_id, 'image_files_erased': erased, 'can_sync_again': freed}
