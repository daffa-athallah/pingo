export interface CheckInOption {
  value: string
  label: string
  allows_comment?: boolean
}

export interface CheckInQuestion {
  id: string
  loop_id: string
  type: 'CONFIRM' | 'CLARIFY' | 'STILL_RELEVANT'
  domain: 'shopping' | 'food' | 'destination'
  summary: string
  question: string
  supporting_images: { url: string; alt: string }[]
  options: CheckInOption[]
  positive?: CheckInOption
  negative?: CheckInOption
  context?: string
}

export interface CheckInResponse {
  response: string
  comment: string | null
}
