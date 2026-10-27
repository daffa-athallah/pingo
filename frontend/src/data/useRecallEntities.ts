import { useEffect, useState } from 'react'
import { getOpenLoopViews, imageUrl } from '../services/api'
import type { OpenLoopViewResponse } from '../services/api'
import { mockEntities } from './mockData'
import type { RecallCategory, RecallEntity } from '../types/recall'
import { verifiedCatalogueImage } from './collectionPresentation'

/** "Elmo's Hamburger Restaurant (Fitzroy North, Melbourne)" -> subject and a short place; qualifiers stay in the full title. */
function splitTitle(title: string, fallbackPlace: string | null): { name: string; place?: string } {
  const subject = title.replace(/^Interested in\s+/i, '')
  const match = subject.match(/^(.*?)\s*\(([^)]*)\)/)
  if (!match) return { name: subject, place: fallbackPlace ?? undefined }
  const parts = match[2].split(',').map((part) => part.trim())
  const short = parts.length <= 2 && !/[\d$~]/.test(match[2])
  return { name: match[1], place: short ? parts.join(', ') : fallbackPlace ?? undefined }
}

export function entityFromLoop(loop: OpenLoopViewResponse): RecallEntity {
  const category = loop.domain as RecallCategory
  const distinctShots = [...new Map(loop.screenshots.map(shot => [shot.evidence_id, shot])).values()]
  const screenshots = distinctShots.map((shot) => ({ id: shot.evidence_id, thumbUrl: imageUrl(shot.image_url, 400), fullUrl: imageUrl(shot.image_url, 1600), summary: shot.summary, timestamp: shot.timestamp }))
  const latest = distinctShots.map(shot => Date.parse(shot.timestamp)).filter(Number.isFinite).sort((a, b) => b - a)[0]
  return {
    id: loop.loop_id,
    category,
    // Loop titles are hypotheses phrased "Interested in ..."; the card shows the subject, the detail keeps the full sentence.
    ...(({ name, place }) => ({ name, location: place }))(splitTitle(loop.title, loop.location)),
    screenshotCount: distinctShots.length,
    inferredIntention: loop.title,
    catalogueImage: verifiedCatalogueImage(loop),
    latestScreenshotAt: latest === undefined ? undefined : new Date(latest).toISOString(),
    screenshots,
  }
}

export type EntitiesState =
  | { status: 'loading'; entities: RecallEntity[] }
  | { status: 'ready'; entities: RecallEntity[]; source: 'zetaris' | 'mock' }
  | { status: 'error'; entities: RecallEntity[]; message: string }

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/** Open Loops from the backend (Zetaris in real mode). Mock data only when VITE_USE_MOCK=true; never a silent fallback. */
export function useRecallEntities(): EntitiesState & { retry: () => void } {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<EntitiesState>(USE_MOCK ? { status: 'ready', entities: mockEntities, source: 'mock' } : { status: 'loading', entities: [] })
  useEffect(() => {
    if (USE_MOCK) return undefined
    setState({ status: 'loading', entities: [] })
    const controller = new AbortController()
    getOpenLoopViews(controller.signal)
      .then((loops) => setState({ status: 'ready', entities: loops.map(entityFromLoop), source: 'zetaris' }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ status: 'error', entities: [], message: error instanceof Error ? error.message : 'Could not load intentions.' })
      })
    return () => controller.abort()
  }, [revision])
  return { ...state, retry: () => setRevision(value => value + 1) }
}
