"""Give a saved place a coordinate: paste a Google Maps link (or "lat, lon") you checked yourself.

Used when the automatic map lookup cannot place a small business. Recall never guesses a location; a person's own pin is a verified source."""
from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app import geocode
from backend.app.bootstrap import live_models

router = APIRouter()


class PinBody(BaseModel):
    link: str = Field(min_length=3, max_length=2000, description='A Google Maps link, or "latitude, longitude"')
    location_id: str | None = Field(default=None, max_length=80, pattern=r'^osm:(node|way|relation):\d+$', description='Set when confirming a place the map search proposed')
    label: str | None = Field(default=None, max_length=300)


@router.post('/api/entities/{entity_id}/location')
async def set_location(request: Request, entity_id: str, body: PinBody):
    state = request.app.state
    if state.mode == 'sample' and not live_models():
        raise HTTPException(status_code=404, detail='Setting a location is available with live models or the real backend.')
    point = geocode.parse_maps_link(body.link, follow=geocode.follow_redirect)
    if point is None:
        raise HTTPException(status_code=422, detail='Could not read a location from that. Paste a Google Maps link, or "latitude, longitude".')
    async with state.write_lock:
        found = state.repository.get_entities([entity_id])
        entity = found[0] if found else None
        if entity is None or entity.domain not in ('food', 'travel'):
            raise HTTPException(status_code=404, detail='Only a saved restaurant or destination can be given a location.')
        updated = replace(entity, metadata=geocode.metadata_from_pin(entity, point[0], point[1], how=(f"OpenStreetMap place '{body.label or body.location_id}' proposed by the map search and confirmed" if body.location_id else 'Google Maps pin or link'), location_id=body.location_id))
        state.repository.save_entity(updated)
        if hasattr(state, 'on_data_changed'):
            state.on_data_changed()
    return {'entity_id': entity_id, 'name': entity.name, 'latitude': point[0], 'longitude': point[1], 'location_id': updated.metadata['location_id'],
            'location_verified': True}


@router.post('/api/entities/{entity_id}/find-location')
async def find_location_for(request: Request, entity_id: str):
    """Ask the Location Agent to find a saved place on the web and verify it on the map. Takes a minute or so (a web search, a model call, a map check)."""
    from backend.app.context_api import _gateway
    from backend.app.location_web import find_and_save
    state = request.app.state
    if state.mode == 'sample' and not live_models():
        raise HTTPException(status_code=404, detail='Finding a location needs live models.')
    async with state.write_lock:
        found = state.repository.get_entities([entity_id])
        if not found or found[0].domain not in ('food', 'travel'):
            raise HTTPException(status_code=404, detail='Only a saved restaurant or destination can be located.')
        async with _gateway() as gateway:
            row = await find_and_save(state.repository, entity_id, gateway)
        if row and row.get('status') == 'resolved' and hasattr(state, 'on_data_changed'):
            state.on_data_changed()
    return {'entity_id': entity_id, 'name': found[0].name, **(row or {'status': 'unavailable', 'reason': 'Nothing was found.'})}
