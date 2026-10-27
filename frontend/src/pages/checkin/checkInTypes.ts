export interface CheckInOption {
  value: string
  label: string
  allows_comment?: boolean
  comment_required?: boolean
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
  response_mode?: 'options'
}

export interface CheckInResponse {
  response: string
  comment: string | null
}

export interface CheckInSubmission {
  ok: boolean
  agent_review?: { state: 'COMPLETED' | 'FAILED_SAFE' | 'SKIPPED' | 'DEFERRED' | 'RUNNING' }
}
