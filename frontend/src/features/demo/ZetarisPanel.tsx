import { useEffect, useState } from 'react'
import { getZetarisProof } from '../../services/runsApi'
import type { ZetarisProof } from '../../services/runsApi'

/** Sample mode does not connect to Zetaris. This shows a read-only capture of the real instance, so the integration can be inspected. */
export default function ZetarisPanel() {
  const [proof, setProof] = useState<ZetarisProof | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getZetarisProof(controller.signal).then(setProof).catch(() => { if (!controller.signal.aborted) setError('The capture could not be loaded.') })
    return () => controller.abort()
  }, [])
  if (error) return <p className="try-error">{error}</p>
  if (!proof) return null
  return <div className="zetaris-panel">
    <h2>Zetaris holds the memory</h2>
    <p>{proof.role}</p>
    <p className="try-note">Captured {new Date(proof.captured_at).toLocaleDateString()} from the real instance, read-only. This sample server itself is offline, with no Zetaris connection.</p>
    <h3>Tables in <code>{proof.namespace}</code></h3>
    <dl className="zetaris-counts">{Object.entries(proof.table_counts).map(([name, count]) => <div key={name}><dt>{name}</dt><dd>{count}</dd></div>)}</dl>
    <h3>Queries the agents run</h3>
    {proof.queries.map(query => <details key={query.role}>
      <summary>{query.role}</summary>
      <p className="try-note">{query.note}</p>
      <pre>{query.sql}</pre>
      <p className="try-note">{query.rows_returned} rows. First: {query.sample.map(row => row.join(' · ')).join(' | ')}</p>
    </details>)}
  </div>
}
