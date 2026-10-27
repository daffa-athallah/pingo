import Mascot from './Mascot'
import type { MascotState } from './Mascot'
import { AGENT_IDS } from './orchestraModel'
import type { AgentId, Frame, Row } from './orchestraModel'

const AGENTS: Record<AgentId, { name: string; question: string; doing: string }> = {
  evidence: { name: 'Evidence', question: 'What is here?', doing: 'Analyzing…' },
  openloop: { name: 'Open Loop', question: 'What’s unfinished?', doing: 'Thinking…' },
  context: { name: 'Context', question: 'Why now?', doing: 'Checking…' },
  critic: { name: 'Critic', question: 'Worth a ping?', doing: 'Evaluating…' },
}
// Seats on the stage and where the conductor's baton points for each.
const ANGLE: Record<AgentId, number> = { evidence: -140, context: -40, openloop: 140, critic: 40 }
const COLUMNS: { id: Row; label: string }[] = [{ id: 'evidence', label: 'Evidence' }, { id: 'entities', label: 'Entities' }, { id: 'loops', label: 'Open Loops' }]
const SIGNAL: Record<'location' | 'calendar' | 'time', string> = { location: '📍 Location', calendar: '📅 Calendar', time: '◷ Time' }

function stateOf(id: AgentId, frame: Frame | null): MascotState {
  if (!frame) return 'idle'
  if (frame.active === id) return 'active'
  if (!frame.involved.includes(id)) return frame.involved.length ? 'rest' : 'idle'
  if (frame.done.includes(id)) return frame.failed && frame.finished ? 'quiet' : 'done'
  return 'idle'
}

/** The four Pingo workers in a small warm room: Zetaris as the shared clipboard, a tiny conductor, and the supporting infrastructure below.
 *  Everything lights up only from the run's real events. */
export default function OrchestraStage({ frame, simulated }: { frame: Frame | null; simulated: boolean }) {
  const hm = frame?.hmem ?? 'idle'
  const model = frame?.model ?? null
  const on = (a: AgentId, b: AgentId) => frame?.active === a || frame?.active === b
  return <div className="scene" aria-label="Pingo agent orchestra">
    <div className="scene-floor" aria-hidden="true" />
    <svg className="scene-plant plant-l" viewBox="0 0 60 70" aria-hidden="true"><path d="M30 68 C26 44 12 36 4 20 C20 22 30 34 30 50 C30 30 36 14 52 6 C50 28 42 42 30 68Z" fill="#7BB872" /><path d="M30 68 V40" stroke="#5E9B58" strokeWidth="2" /><rect x="18" y="56" width="24" height="14" rx="4" fill="#E9A77E" /></svg>
    <svg className="scene-plant plant-r" viewBox="0 0 60 70" aria-hidden="true"><path d="M30 68 C34 44 48 36 56 20 C40 22 30 34 30 50 C30 30 24 14 8 6 C10 28 18 42 30 68Z" fill="#7BB872" /><rect x="18" y="56" width="24" height="14" rx="4" fill="#E9A77E" /></svg>

    <div className="clipboard" aria-label="Zetaris, shared state">
      <i className="clip" aria-hidden="true" />
      <div className="clipboard-cols">
        {COLUMNS.map((c) => <div key={c.id} className={`clip-col${frame?.lit.includes(c.id) ? ' is-lit' : ''}`}><b>{c.label}</b>{[0, 1, 2].map((n) => <span key={n}><u />{' '}<s /></span>)}</div>)}
      </div>
      <div className="clipboard-tag"><strong>Zetaris</strong> · Shared state</div>
    </div>

    <svg className="scene-arrows" viewBox="0 0 390 430" aria-hidden="true">
      <path className={`arrow${frame?.lit.includes('evidence') ? ' is-on' : ''}`} d="M96 112 C96 100 118 96 146 96" />
      <path className={`arrow${frame?.active === 'context' ? ' is-on' : ''}`} d="M294 112 C294 100 272 96 244 96" />
      <path className={`arrow${on('evidence', 'openloop') ? ' is-on' : ''}`} d="M48 168 C14 198 14 232 48 262" />
      <path className={`arrow${on('context', 'critic') ? ' is-on' : ''}`} d="M342 168 C376 198 376 232 342 262" />
      <path className={`arrow${on('openloop', 'critic') || frame?.revision ? ' is-on' : ''}`} d="M140 292 C170 306 220 306 250 292" />
    </svg>

    {AGENT_IDS.map((id) => {
      const s = stateOf(id, frame)
      return <div key={id} className={`seat seat-${id} is-${s}`}>
        <div className="seat-art"><Mascot id={id} state={s} />{s === 'done' ? <b className="seat-check" aria-hidden="true">✓</b> : null}</div>
        <strong>{AGENTS[id].name}</strong><span>{AGENTS[id].question}</span>
        {s === 'active' ? <em className="bubble">{AGENTS[id].doing}</em> : null}
        {id === 'critic' && frame?.revision ? <em className="bubble is-note">Asking Open Loop to revise</em> : null}
        {id === 'context' && frame?.signals.length ? <div className="signals" aria-label={simulated ? 'Simulated context signals' : 'Context signals'}>{frame.signals.map((x) => <em key={x}>{SIGNAL[x]}</em>)}{simulated ? <small>simulated</small> : null}</div> : null}
      </div>
    })}
    <div className="conductor" aria-label="Conductor: the orchestrator, not an agent" title="Conductor (orchestrator)">
      <span className="conductor-dot" />
      {frame?.active ? <span key={frame.active + (frame.event?.seq ?? '')} className="baton" style={{ ['--angle' as string]: `${ANGLE[frame.active]}deg` }} /> : null}
    </div>

    <div className="infra">
      <div className={`cube${model ? ' is-lit' : ''}`}><i className="cube-icon icon-route" aria-hidden="true" /><strong>Nightshift</strong><span>Model routing</span>{model ? <em>{model.label} ✓</em> : null}</div>
      <div className={`cube${model || hm !== 'idle' ? ' is-lit' : ''}`}><i className="cube-icon icon-m" aria-hidden="true" /><strong>Meterless</strong><span>AI infrastructure</span></div>
      <div className={`cube${hm !== 'idle' ? ' is-lit' : ''}${hm === 'unavailable' ? ' is-off' : ''}`}><i className="cube-icon icon-mem" aria-hidden="true" /><strong>H-MEM</strong><span>Learned preferences</span>{hm !== 'idle' ? <em>{hm === 'query' ? 'recalled' : hm === 'store' ? 'remembered' : 'unavailable'}</em> : null}</div>
    </div>
  </div>
}
