// Mirrors the backend orchestrator output exactly (backend/app/orchestration/recall.py, domain/trace.py).
// Anything fetched later from GET /runs/:run_id can be passed in unchanged.

export interface Receipt {
  requested_model: string | null
  routed_model: string | null
  provider: string | null
}

export interface TraceEvent {
  run_id: string | null
  timestamp: string | null
  agent: string
  action: string
  reason: string
  input_refs: string[]
  next_step: string | null
  output_ref: string | null
  receipt: Receipt | null
}

export type RunType = 'EVIDENCE_INGESTION' | 'CONTEXT_EVALUATION'
export type FinalAction = 'STORED' | 'SURFACE' | 'STAY_SILENT' | 'ASK' | 'FAILED_SAFE'

export interface RunResult {
  run_id: string
  run_type: RunType
  final_action: FinalAction
  loop_id: string | null
  evidence_id: string | null
  message_payload: Record<string, unknown> | null
  question: string | null
  error: string | null
  revision_count: number
  verification_count: number
  trace_events: TraceEvent[]
}

/** Presentation-only extras for fixtures. Live runs do not need them. */
export interface Annotations {
  /** Short bold line under a node, keyed `${runIndex}:${eventIndex}`. */
  headlines?: Record<string, string>
  /** Detail line for the input node of each run, keyed by runIndex. */
  inputs?: Record<number, { title?: string; detail?: string }>
  /** Detail for the shared-state node of a context run, keyed by runIndex. */
  state?: Record<number, string>
}

export interface DemoRun {
  id: string
  label: string
  blurb: string
  runs: RunResult[]
  annotations: Annotations
}
