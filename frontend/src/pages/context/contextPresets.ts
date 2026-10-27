import type { ContextEntityResponse, OpenLoopViewResponse } from '../../services/api'

export interface VerifiedPlace {
  entityId: string
  name: string
  domain: string
  latitude: number
  longitude: number
  source: string
  loopIds: string[]
  evidenceIds: string[]
}

/** Mirror the existing geographic retrieval's requirements, without claiming final agent eligibility. */
export function contextPlaces(entities: ContextEntityResponse[], loops: OpenLoopViewResponse[]) {
  const places: VerifiedPlace[] = []
  const unavailable: { entityId: string; name: string; reason: string }[] = []
  for (const entity of entities) {
    if (!['food', 'shopping', 'travel'].includes(entity.domain)) continue
    const meta = entity.metadata ?? {}
    const linked = loops.filter(loop => ['OPEN', 'ACTIVE'].includes(loop.status) && loop.screenshots.length > 0 && loop.entities.some(item => item.entity_id === entity.entity_id))
    let reason = ''
    const latitude = Number(meta.latitude), longitude = Number(meta.longitude)
    if (meta.location_verified?.toLowerCase() !== 'true' || !meta.location_source?.trim()
      || !meta.latitude?.trim() || !meta.longitude?.trim() || !Number.isFinite(latitude) || !Number.isFinite(longitude)
      || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) reason = 'No verified coordinates and source. Proximity cannot be evaluated.'
    else if (entity.domain === 'shopping' && !(meta.location_role === 'store' && meta.store_name?.trim())) reason = 'No verified physical store association. Product location does not establish a shop or inventory.'
    else if (!linked.length) reason = 'No active linked intention with supporting screenshot evidence.'
    if (reason) { unavailable.push({ entityId: entity.entity_id, name: entity.name, reason }); continue }
    places.push({ entityId: entity.entity_id, name: entity.name, domain: entity.domain, latitude, longitude, source: meta.location_source,
      loopIds: linked.map(loop => loop.loop_id), evidenceIds: [...new Set(linked.flatMap(loop => loop.screenshots.map(shot => shot.evidence_id)))] })
  }
  return { places, unavailable }
}

/** Great-circle offset in metres from an actually verified location; not entity geocoding. */
export function offsetLocation(latitude: number, longitude: number, meters: number) {
  const delta = meters / 6371008.8
  const lat = latitude * Math.PI / 180, lon = longitude * Math.PI / 180
  const target = Math.asin(Math.sin(lat) * Math.cos(delta) + Math.cos(lat) * Math.sin(delta))
  const targetLon = lon + Math.atan2(0, Math.cos(delta) - Math.sin(lat) * Math.sin(target))
  return { latitude: target * 180 / Math.PI, longitude: ((targetLon * 180 / Math.PI + 540) % 360) - 180 }
}
