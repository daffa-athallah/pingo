export type RecallCategory = 'food' | 'shopping' | 'travel'

export interface RecallEntity {
  id: string
  category: RecallCategory
  name: string
  location?: string
  screenshotCount: number
  inferredIntention: string
  imageUrl?: string
  catalogueImage?: { url: string; source: string; entityId: string; alt: string; objectPosition?: string }
  latestScreenshotAt?: string
  /** The user's own supporting screenshots, when the backend provides them. */
  screenshots?: { id: string; thumbUrl: string; fullUrl: string; summary: string; timestamp?: string }[]
}

export interface TriggeredRecall {
  id: string
  category: RecallCategory
  title: string
  message: string
  reason: string
  entityIds: string[]
}
