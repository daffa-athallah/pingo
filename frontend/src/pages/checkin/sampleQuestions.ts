import type { CheckInQuestion } from './checkInTypes'

export const sampleQuestions: CheckInQuestion[] = [
  {
    id: 'sample_shopping', loop_id: 'sample_outerwear', type: 'CLARIFY', domain: 'shopping',
    summary: "You've been saving brown jackets and outfits lately.",
    question: 'Is brown outerwear something you’re interested in?',
    context: 'A few of your saved looks have this in common. What best describes your interest?',
    supporting_images: [
      { url: '/images/checkin/brown-blazer.jpg', alt: 'A tailored brown blazer' },
      { url: '/images/checkin/brown-shirt.jpg', alt: 'A short-sleeved chocolate brown shirt' },
      { url: '/images/checkin/brown-outfit.png', alt: 'A brown suede blazer styled with a dark shirt' },
    ],
    positive: { value: 'yes', label: 'Yes, that’s right' }, negative: { value: 'no', label: 'Not quite' },
    options: [
      { value: 'buying', label: 'Thinking of buying' },
      { value: 'comparing', label: 'Comparing options' },
      { value: 'inspiration', label: 'Just inspiration' },
      { value: 'other', label: 'Something else', allows_comment: true },
    ],
  },
  {
    id: 'sample_food', loop_id: 'sample_carlton', type: 'CONFIRM', domain: 'food',
    summary: "You've saved several restaurants around Carlton.",
    question: 'Are you thinking about trying some of them soon?',
    context: 'These saves might be places for your next meal out. You can confirm that, or tell me what you had in mind.',
    supporting_images: [],
    positive: { value: 'yes', label: 'Yes, I am' }, negative: { value: 'no', label: 'Not right now' },
    options: [
      { value: 'soon', label: 'Planning a visit soon' },
      { value: 'inspiration', label: 'Saving ideas for later' },
      { value: 'other', label: 'Something else', allows_comment: true },
    ],
  },
  {
    id: 'sample_destination', loop_id: 'sample_japan', type: 'STILL_RELEVANT', domain: 'destination',
    summary: "Japan keeps showing up in things you've saved.",
    question: 'Is a Japan trip something you’re considering?',
    context: 'Your saves suggest Japan might be on your mind. Is it a plan, a possibility, or simply a little inspiration?',
    supporting_images: [],
    positive: { value: 'yes', label: 'Still interested' }, negative: { value: 'no', label: 'Not anymore' },
    options: [
      { value: 'planning', label: 'Planning a trip' },
      { value: 'someday', label: 'Maybe someday' },
      { value: 'inspiration', label: 'Just inspiration' },
      { value: 'other', label: 'Something else', allows_comment: true },
    ],
  },
]
