import { shortId } from './traceAdapter'
import type { Timeline } from './traceAdapter'

const LABELS: Record<string, string> = { SURFACE: 'Surfaced', STAY_SILENT: 'Stayed silent', ASK: 'Asked', FAILED_SAFE: 'Stopped safely', STORED: 'Stored', RUNNING: 'In progress' }

export default function RunSummary({ timeline }: { timeline: Timeline }) {
  const { summary } = timeline
  const quiet = summary.finalAction === 'STAY_SILENT'
  return (
    <section className="aa-summary" aria-label="Run summary">
      <div>
        <p className="aa-summary-id">{summary.runIds.map(shortId).join(' → ')}</p>
        <p className="aa-summary-stats">
          {summary.steps} steps · {summary.revisions} {summary.revisions === 1 ? 'revision' : 'revisions'} · {summary.verifications} {summary.verifications === 1 ? 'verification' : 'verifications'}
        </p>
      </div>
      <span className={`aa-final aa-final-${summary.finalAction.toLowerCase().replace('_', '-')}${quiet ? ' is-quiet' : ''}`}>{LABELS[summary.finalAction] ?? summary.finalAction}</span>
    </section>
  )
}
