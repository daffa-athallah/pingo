import type { DemoRun, Receipt, TraceEvent } from './types'

// Demo data only. Shapes match the backend RunResult / TraceEvent exactly, so this file can be replaced by
// GET /runs/:run_id (or the JSONL trace) without touching the visualization.
// Reasons are taken from real Nightshift runs; the Zara and Carlton sequences are curated demo traces.

const NEMOTRON: Receipt = { requested_model: 'nvidia/nemotron-3-ultra-550b-a55b', routed_model: 'nvidia/nemotron-3-ultra-550b-a55b', provider: 'nvidia' }
const GPT4O_MINI: Receipt = { requested_model: 'gpt-4o-mini', routed_model: 'gpt-4o-mini', provider: 'openai' }

function event(run_id: string, minute: number, e: Omit<TraceEvent, 'run_id' | 'timestamp'>): TraceEvent {
  return { run_id, timestamp: `2026-10-25T07:${String(minute).padStart(2, '0')}:00+00:00`, ...e }
}

const OMB_INGEST = 'run_68c48e3247c6'
const OMB_CONTEXT = 'run_3b3d227d0847'
const ZARA = 'run_8ec0b92017d4'
const CARLTON = 'run_5d1c9a07b2e4'

const OMB_TITLE = 'Interested in OMB Burger'

export const demoRuns: DemoRun[] = [
  {
    id: 'omb-burger',
    label: 'OMB Burger',
    blurb: 'A saved screenshot becomes an intention, then surfaces when a late supper is planned nearby.',
    annotations: {
      headlines: { '0:0': 'OMB Burger', '0:2': OMB_TITLE, '1:0': 'Late supper · Melbourne CBD' },
      inputs: { 0: { title: 'Screenshot', detail: 'IMG_8922.PNG' }, 1: { title: 'Calendar event', detail: 'Late supper with Sam · 22:30' } },
      state: { 1: 'Open loop “Interested in OMB Burger” and its evidence' },
    },
    runs: [
      {
        run_id: OMB_INGEST, run_type: 'EVIDENCE_INGESTION', final_action: 'STORED', loop_id: 'loop_4173bc6a09f6', evidence_id: 'ev_23eb26880e81',
        message_payload: null, question: null, error: null, revision_count: 0, verification_count: 0,
        trace_events: [
          event(OMB_INGEST, 31, { agent: 'EVIDENCE', action: 'EXTRACT', reason: 'Extracted OMB Burger from screenshot.', input_refs: ['image:IMG_8922.PNG'], next_step: 'INGESTION', output_ref: null, receipt: GPT4O_MINI }),
          event(OMB_INGEST, 31, { agent: 'INGESTION', action: 'STORE', reason: 'Stored evidence with 1 entities.', input_refs: ['image:IMG_8922.PNG'], next_step: 'OPEN_LOOP', output_ref: 'evidence:ev_23eb26880e81', receipt: null }),
          event(OMB_INGEST, 32, { agent: 'OPEN_LOOP', action: 'CREATE', reason: "Screenshot saved promoting OMB Burger's halal, late-night, under-$10 offer in Melbourne CBD; suggests interest in this venue.", input_refs: ['evidence:ev_23eb26880e81', 'entity:ent_81b7feb45234'], next_step: 'STOP', output_ref: 'loop:loop_4173bc6a09f6', receipt: NEMOTRON }),
        ],
      },
      {
        run_id: OMB_CONTEXT, run_type: 'CONTEXT_EVALUATION', final_action: 'SURFACE', loop_id: 'loop_4173bc6a09f6', evidence_id: null,
        message_payload: { loop_id: 'loop_4173bc6a09f6', title: OMB_TITLE, reason: 'Late supper calendar event in Melbourne CBD aligns with interest in OMB Burger (halal, late-night, under $10).', evidence_ids: ['ev_23eb26880e81'], context_ids: ['ctx_supper'] },
        question: null, error: null, revision_count: 0, verification_count: 0,
        trace_events: [
          event(OMB_CONTEXT, 38, { agent: 'CONTEXT', action: 'MATCH', reason: 'Calendar event for late supper in Melbourne CBD matches open loop for OMB Burger (halal, late-night, under $10) in same area.', input_refs: ['context:ctx_supper', 'loop:loop_4173bc6a09f6'], next_step: 'CRITIC', output_ref: 'loop:loop_4173bc6a09f6', receipt: NEMOTRON }),
          event(OMB_CONTEXT, 38, { agent: 'CRITIC', action: 'SURFACE', reason: 'Late supper calendar event in Melbourne CBD aligns with interest in OMB Burger (halal, late-night, under $10).', input_refs: ['loop:loop_4173bc6a09f6', 'context:ctx_supper', 'evidence:ev_23eb26880e81'], next_step: 'OUTPUT', output_ref: 'loop:loop_4173bc6a09f6', receipt: NEMOTRON }),
        ],
      },
    ],
  },
  {
    id: 'zara-self-correction',
    label: 'Zara self-correction',
    blurb: 'The Critic rejects an over-specific intention and sends it back to Open Loop before anything reaches the user.',
    annotations: {
      headlines: { '0:0': 'Shopping trip · Chadstone', '0:1': 'Buy this Zara jacket tomorrow', '0:2': 'Interested in this Zara brown jacket', '0:3': 'Interested in this Zara brown jacket' },
      inputs: { 0: { title: 'Calendar event', detail: 'Shopping trip · 14:00' } },
      state: { 0: 'Open loop “Buy this Zara jacket tomorrow” and a Zara product page' },
    },
    runs: [{
      run_id: ZARA, run_type: 'CONTEXT_EVALUATION', final_action: 'SURFACE', loop_id: 'loop_buy', evidence_id: null,
      message_payload: { loop_id: 'loop_buy', title: 'Interested in this Zara brown jacket', reason: 'Shopping trip tomorrow at Chadstone aligns with interest in brown Zara jacket seen yesterday; product page evidence supports intention.', evidence_ids: ['ev_zara'], context_ids: ['ctx_mall'] },
      question: null, error: null, revision_count: 1, verification_count: 0,
      trace_events: [
        event(ZARA, 38, { agent: 'CONTEXT', action: 'MATCH', reason: 'Calendar event for shopping trip tomorrow matches open loop to buy Zara jacket tomorrow.', input_refs: ['context:ctx_mall', 'loop:loop_buy'], next_step: 'CRITIC', output_ref: 'loop:loop_buy', receipt: NEMOTRON }),
        event(ZARA, 38, { agent: 'CRITIC', action: 'REQUEST_REVISION', reason: 'Loop title states a specific purchase plan for tomorrow, but evidence only shows a Zara product page view — no intent to buy or timing indicated.', input_refs: ['loop:loop_buy', 'context:ctx_mall', 'evidence:ev_zara'], next_step: 'OPEN_LOOP', output_ref: null, receipt: NEMOTRON }),
        event(ZARA, 38, { agent: 'OPEN_LOOP', action: 'REVISE', reason: 'Product page screenshot indicates interest in this Zara brown jacket; revised title removes unsupported purchase plan and timing.', input_refs: ['loop:loop_buy', 'evidence:ev_zara'], next_step: 'CRITIC', output_ref: 'loop:loop_buy', receipt: NEMOTRON }),
        event(ZARA, 38, { agent: 'CRITIC', action: 'SURFACE', reason: 'Shopping trip tomorrow at Chadstone aligns with interest in brown Zara jacket seen yesterday; product page evidence supports intention.', input_refs: ['loop:loop_buy', 'context:ctx_mall', 'evidence:ev_zara'], next_step: 'OUTPUT', output_ref: 'loop:loop_buy', receipt: NEMOTRON }),
      ],
    }],
  },
  {
    id: 'restraint',
    label: 'Restraint',
    blurb: 'Something nearby is technically related, and pingo correctly decides not to interrupt.',
    annotations: {
      headlines: { '0:0': 'Pick up dry cleaning · Carlton', '0:1': 'Try restaurants in Carlton' },
      inputs: { 0: { title: 'Calendar event', detail: 'Pick up dry cleaning · 08:30' } },
      state: { 0: 'Open loop “Try restaurants in Carlton” and three saved restaurants' },
    },
    runs: [{
      run_id: CARLTON, run_type: 'CONTEXT_EVALUATION', final_action: 'STAY_SILENT', loop_id: 'loop_carlton', evidence_id: null,
      message_payload: null, question: null, error: null, revision_count: 0, verification_count: 0,
      trace_events: [
        event(CARLTON, 41, { agent: 'CONTEXT', action: 'MATCH', reason: 'The errand is also in Carlton.', input_refs: ['context:ctx_errand', 'loop:loop_carlton'], next_step: 'CRITIC', output_ref: 'loop:loop_carlton', receipt: NEMOTRON }),
        event(CARLTON, 41, { agent: 'CRITIC', action: 'STAY_SILENT', reason: "Errand in Carlton doesn't indicate dining intent; weak context for restaurant loop.", input_refs: ['loop:loop_carlton', 'context:ctx_errand', 'evidence:ev_c0', 'evidence:ev_c1', 'evidence:ev_c2'], next_step: 'STOP', output_ref: null, receipt: NEMOTRON }),
      ],
    }],
  },
]
