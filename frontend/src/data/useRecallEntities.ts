import { useEffect, useState } from 'react'
import { getOpenLoopViews, imageUrl } from '../services/api'
import type { OpenLoopViewResponse } from '../services/api'
import { mockEntities } from './mockData'
import restaurant from '../assets/images/recall/restaurant.jpg'
import jacket from '../assets/images/recall/jacket.jpg'
import japan from '../assets/images/recall/japan.jpg'
import tokyo from '../assets/images/recall/tokyo.jpg'
import gallery from '../assets/images/recall/gallery.jpg'
import type { RecallCategory, RecallEntity } from '../types/recall'

// Stock photographs are decorative placeholders by category, not the user's screenshots.
const STOCK: Record<RecallCategory, string[]> = {
  food: [restaurant], // one neutral venue photo: a specific dish would often contradict the place
  shopping: [jacket],
  travel: [japan, tokyo, gallery],
}

function stockFor(category: RecallCategory, id: string): string {
  const pool = STOCK[category]
  let hash = 0
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return pool[hash % pool.length]
}

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
  return {
    id: loop.loop_id,
    category,
    // Loop titles are hypotheses phrased "Interested in ..."; the card shows the subject, the detail keeps the full sentence.
    ...(({ name, place }) => ({ name, location: place }))(splitTitle(loop.title, loop.location)),
    screenshotCount: loop.screenshot_count,
    inferredIntention: loop.title,
    imageUrl: stockFor(category, loop.loop_id),
    screenshots: loop.screenshots.map((shot) => ({ id: shot.evidence_id, thumbUrl: imageUrl(shot.image_url, 400), fullUrl: imageUrl(shot.image_url, 1600), summary: shot.summary })),
  }
}

export type EntitiesState =
  | { status: 'loading'; entities: RecallEntity[] }
  | { status: 'ready'; entities: RecallEntity[]; source: 'zetaris' | 'mock' }
  | { status: 'error'; entities: RecallEntity[]; message: string }

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

/** Open Loops from the backend (Zetaris in real mode). Mock data only when VITE_USE_MOCK=true; never a silent fallback. */
export function useRecallEntities(): EntitiesState {
  const [state, setState] = useState<EntitiesState>(USE_MOCK ? { status: 'ready', entities: mockEntities, source: 'mock' } : { status: 'loading', entities: [] })
  const [revision, setRevision] = useState(0)
  useEffect(() => {  // the recorded-example guide announces that the sample data changed
    const refresh = () => setRevision((value) => value + 1)
    window.addEventListener('recall:data-changed', refresh)
    return () => window.removeEventListener('recall:data-changed', refresh)
  }, [])
  useEffect(() => {
    if (USE_MOCK) return undefined
    const controller = new AbortController()
    getOpenLoopViews(controller.signal)
      .then((loops) => setState({ status: 'ready', entities: loops.map(entityFromLoop), source: 'zetaris' }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ status: 'error', entities: [], message: error instanceof Error ? error.message : 'Could not load intentions.' })
      })
    return () => controller.abort()
  }, [revision])
  return state
}
