import type { RecallEntity } from '../types/recall'
import type { OpenLoopViewResponse } from '../services/api'

export type CollectionSort = 'recent' | 'screenshots'

/** Presentation URLs may be public HTTPS or app media; never laptop file paths or data URLs. */
function isMediaUrl(value: string): boolean {
  if (/^\/(?:media|images|catalogue)\//.test(value)) return !value.includes('..') && !value.startsWith('//')
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password
  } catch { return false }
}

function isPublicSource(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password
  } catch { return false }
}

export function verifiedCatalogueImage(loop: OpenLoopViewResponse): RecallEntity['catalogueImage'] {
  // A multi-entity hypothesis has no unambiguous representative product/place.
  if (loop.entities.length !== 1) return undefined
  const image = loop.catalogue_images?.find(item => item.entity_id === loop.entities[0].entity_id
    && item.catalogue_image_verified === true && isPublicSource(item.catalogue_image_source)
    && item.alt?.trim() && isMediaUrl(item.catalogue_image_url))
  if (!image) return undefined
  return { url: image.catalogue_image_url, source: image.catalogue_image_source,
    entityId: image.entity_id, alt: image.alt, objectPosition: image.object_position }
}

export function sortCollection(items: RecallEntity[], sort: CollectionSort): RecallEntity[] {
  const timestamp = (item: RecallEntity) => {
    const value = Date.parse(item.latestScreenshotAt ?? '')
    return Number.isFinite(value) ? value : -Infinity
  }
  return [...items].sort((a, b) => {
    if (sort === 'screenshots' && a.screenshotCount !== b.screenshotCount) return b.screenshotCount - a.screenshotCount
    const first = timestamp(a), second = timestamp(b)
    if (first !== second) return first > second ? -1 : 1
    return a.id.localeCompare(b.id)
  })
}
