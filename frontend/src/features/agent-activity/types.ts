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
  /** Position within the run (1-based). Present on runs recorded while they execute. */
  seq?: number
  /** Structured inputs, retrievals, decisions and state changes for this step. Never model reasoning. */
  detail?: Record<string, unknown> | null
}

export type RunType = 'EVIDENCE_INGESTION' | 'CONTEXT_EVALUATION'
/** Who produced a run: live = real models, scripted = the credential-free sample fixture, recorded = a captured real run replayed.
 *  illustration = hand-written fixture shipped with the frontend; it is not a run at all. */
export type Provenance = 'live' | 'scripted' | 'recorded'
export type RunProvenance = Provenance | 'illustration'
export type RunStatus = 'running' | 'done' | 'failed'
export type FinalAction = 'STORED' | 'SURFACE' | 'STAY_SILENT' | 'ASK' | 'FAILED_SAFE'

export interface RunResult {
  run_id: string
  run_type: RunType
  /** null while the run is still executing */
  final_action: FinalAction | null
  loop_id: string | null
  evidence_id: string | null
  message_payload: Record<string, unknown> | null
  question: string | null
  error: string | null
  revision_count: number
  verification_count: number
  trace_events: TraceEvent[]
}

/** A run that has finished and therefore has a final decision. */
export type FinishedRun = RunResult & { final_action: FinalAction }

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
  /** Missing means the static illustrations in demoRuns.ts. */
  provenance?: RunProvenance
  status?: RunStatus
  workspace?: string
}
