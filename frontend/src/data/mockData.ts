import type { RecallCategory, RecallEntity } from '../types/recall'
import ramen from '../assets/images/recall/ramen.jpg'
import pasta from '../assets/images/recall/pasta.jpg'
import dumplings from '../assets/images/recall/dumplings.jpg'
import coffee from '../assets/images/recall/coffee.jpg'
import restaurant from '../assets/images/recall/restaurant.jpg'
import jacket from '../assets/images/recall/jacket.jpg'
import japan from '../assets/images/recall/japan.jpg'
import tokyo from '../assets/images/recall/tokyo.jpg'
import gallery from '../assets/images/recall/gallery.jpg'

// Local stock photographs are visual placeholders, not actual venue/product evidence.
// Replace image references here when real assets are available.
export const categories: {
  id: RecallCategory
  name: string
  itemLabel: string
}[] = [
  { id: 'food', name: 'Food', itemLabel: 'places' },
  { id: 'shopping', name: 'Shopping', itemLabel: 'products' },
  { id: 'travel', name: 'Destination', itemLabel: 'places' },
]

// Development fixtures only; no backend, calendar, or location integration.
export const mockEntities: RecallEntity[] = [
  { id: 'food-ramen-a', category: 'food', name: 'Ramen A', location: 'Carlton', screenshotCount: 5, imageUrl: ramen, inferredIntention: "You’re looking for ramen places in Carlton to try, possibly for dinner with Alex." },
  { id: 'food-pasta-b', category: 'food', name: 'Pasta B', location: 'Carlton', screenshotCount: 3, imageUrl: pasta, inferredIntention: "You’ve been saving Italian restaurants in Carlton to try, likely for a casual dinner." },
  { id: 'food-dumpling-c', category: 'food', name: 'Dumpling C', location: 'Carlton', screenshotCount: 4, imageUrl: dumplings, inferredIntention: 'You seem interested in trying dumplings in Carlton, perhaps for a relaxed meal with friends.' },
  { id: 'food-good-measure', category: 'food', name: 'Good Measure', location: 'Carlton', screenshotCount: 2, imageUrl: coffee, inferredIntention: 'You seem to be keeping this café in mind for your next coffee catch-up.' },
  { id: 'food-tipo-00', category: 'food', name: 'Tipo 00', location: 'Carlton', screenshotCount: 3, imageUrl: restaurant, inferredIntention: 'You seem interested in a cosy Italian restaurant for a future dinner.' },
  { id: 'shopping-zara-brown-jacket', category: 'shopping', name: 'Zara Brown Jacket', screenshotCount: 3, imageUrl: jacket, inferredIntention: 'You seem interested in brown outerwear, possibly as something to buy or compare.' },
  { id: 'shopping-uniqlo-overshirt', category: 'shopping', name: 'Uniqlo Brown Overshirt', screenshotCount: 2, imageUrl: jacket, inferredIntention: 'You seem to be considering a casual overshirt as a lighter everyday layer.' },
  { id: 'shopping-cos-jacket', category: 'shopping', name: 'COS Brown Jacket', screenshotCount: 2, imageUrl: jacket, inferredIntention: 'You seem to be comparing simple brown jackets to find a shape you like.' },
  { id: 'travel-teamlab-tokyo', category: 'travel', name: 'TeamLab Tokyo', location: 'Tokyo, Japan', screenshotCount: 2, imageUrl: gallery, inferredIntention: 'You seem interested in visiting TeamLab during a future Japan trip.' },
  { id: 'travel-shibuya-sky', category: 'travel', name: 'Shibuya Sky', location: 'Tokyo, Japan', screenshotCount: 3, imageUrl: tokyo, inferredIntention: 'You seem interested in seeing Tokyo from above, possibly around sunset.' },
  { id: 'travel-tokyo-cafe', category: 'travel', name: 'Tokyo Cafe', location: 'Tokyo, Japan', screenshotCount: 1, imageUrl: coffee, inferredIntention: 'You seem to be collecting café stops for a future visit to Tokyo.' },
  { id: 'travel-kyoto-temple', category: 'travel', name: 'Kyoto Temple', location: 'Kyoto, Japan', screenshotCount: 2, imageUrl: japan, inferredIntention: 'You seem interested in making time for Kyoto’s temples during your Japan trip.' },
]
