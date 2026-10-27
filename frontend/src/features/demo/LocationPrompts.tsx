import { useState } from 'react'
import { setEntityLocation } from '../../services/runsApi'
import type { UploadOutcome } from '../../services/runsApi'

const DONE = new Set(['resolved', 'located'])
const QUIET = new Set(['skipped', 'deferred', 'skipped_private_or_ungrounded'])  // nothing to show: not a physical place, private, or left for a later pass
export type PlaceRow = NonNullable<UploadOutcome['locations']>[number]
/** A place the person can still do something about: the automatic lookup did not settle it. */
export const needsLocation = (row: PlaceRow) => Boolean(row.name) && !DONE.has(row.status) && !QUIET.has(row.status)

/** After a sync: where each saved place was found, or a way to give an unplaced one a location (confirm a proposed place, or paste a Maps link). */
export default function LocationPrompts({ locations }: { locations: UploadOutcome['locations'] }) {
  const [pins, setPins] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const rows = (locations ?? []).filter((row) => row.name && !QUIET.has(row.status))
  if (!rows.length) return null
  const save = async (entityId: string, link: string, pick?: { location_id: string; label: string }) => {
    setErrors((v) => ({ ...v, [entityId]: '' }))
    try {
      const r = await setEntityLocation(entityId, link, pick)
      setSaved((v) => ({ ...v, [entityId]: `${r.latitude.toFixed(5)}, ${r.longitude.toFixed(5)}` }))
    } catch (err) { setErrors((v) => ({ ...v, [entityId]: err instanceof Error ? err.message : 'Could not save.' })) }
  }
  return <>{rows.map((place) => (
    <div key={place.entity_id} className="demo-location">
      {!DONE.has(place.status) ? (
        <>
          <p><strong>{place.name}</strong>: {place.reason ?? (place.candidates?.length ? 'the map has no exact match.' : 'the map has no match, so nearby reminders are off for it.')}{place.candidates?.length ? ' Is it one of these?' : ''}</p>
          {!saved[place.entity_id] && place.candidates?.map((c) => (
            <button key={c.location_id} type="button" className="demo-candidate" onClick={() => void save(place.entity_id, `${c.lat}, ${c.lon}`, { location_id: c.location_id, label: c.label })}>Use this place: {c.label}</button>
          ))}
          {saved[place.entity_id] ? <p className="demo-ok">Saved: {saved[place.entity_id]}</p> : (
            <form onSubmit={(e) => { e.preventDefault(); void save(place.entity_id, pins[place.entity_id] ?? '') }}>
              <p className="demo-note">Not there? Paste a Google Maps link (or “lat, lon”) to turn nearby reminders on.</p>
              <input value={pins[place.entity_id] ?? ''} onChange={(e) => setPins((v) => ({ ...v, [place.entity_id]: e.target.value }))} placeholder="https://maps.app.goo.gl/… or -37.9187, 145.1286" aria-label={`Location of ${place.name}`} />
              <button type="submit" className="demo-button is-quiet">Save location</button>
              {errors[place.entity_id] ? <span className="demo-error" role="alert">{errors[place.entity_id]}</span> : null}
            </form>)}
        </>
      ) : <p><strong>{place.name}</strong>: located at {Number(place.latitude).toFixed(5)}, {Number(place.longitude).toFixed(5)} ({place.status === 'resolved' ? 'found on the map' : 'already saved'}). Nearby reminders are on.</p>}
    </div>
  ))}</>
}
