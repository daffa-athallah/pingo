export type RecallCategory = 'food' | 'shopping' | 'travel'

export interface RecallEntity {
  id: string
  category: RecallCategory
  name: string
  location?: string
  screenshotCount: number
  inferredIntention: string
  imageUrl?: string
}

export interface TriggeredRecall {
  id: string
  category: RecallCategory
  title: string
  message: string
  reason: string
  entityIds: string[]
}
