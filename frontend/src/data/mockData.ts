import type { RecallCategory, RecallEntity } from '../types/recall'

// Temporary development fixtures, not agent-generated results.
export const categories: { id: RecallCategory; name: string }[] = [
  { id: 'food', name: 'Food' },
  { id: 'shopping', name: 'Shopping' },
  { id: 'travel', name: 'Travel' },
]

export const mockEntities: RecallEntity[] = [
  {
    id: 'food-ramen-a',
    category: 'food',
    name: 'Ramen A',
    location: 'Carlton',
    screenshotCount: 5,
    inferredIntention: 'Try a ramen spot in Carlton.',
  },
  {
    id: 'shopping-zara-brown-jacket',
    category: 'shopping',
    name: 'Zara Brown Jacket',
    screenshotCount: 3,
    inferredIntention: 'Find a brown jacket.',
  },
  {
    id: 'travel-teamlab-tokyo',
    category: 'travel',
    name: 'TeamLab Tokyo',
    screenshotCount: 2,
    inferredIntention: 'Visit TeamLab on a future trip to Tokyo.',
  },
]
