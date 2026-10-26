import { useEffect, useState } from 'react'
import { getIntegrationStatus, getRuns } from '../../services/api'
import type { IntegrationStatusResponse, SavedRunResponse } from '../../services/api'
import AgentActivity from './AgentActivity'
import type { DemoRun } from './types'

const LABELS: Record<string, string> = { A_relevant: 'Relevant context', B_restraint: 'Restraint', revision: 'Revision' }

function toDemo(run: SavedRunResponse): DemoRun {
  const event = run.context_event
  const place = [event?.location_name, event?.city].filter(Boolean).join(', ')
  const detail = run.kind === 'revision_fixture'
    ? 'Synthetic over-specific loop (test fixture) with a synthetic calendar event'
    : `${event?.title ?? 'Calendar event'}${place ? ` · ${place}` : ''} (synthetic test input)`
  const blurb = run.kind === 'revision_fixture'
    ? `Controlled fixture: the loop "${run.original_title}" says more than the evidence shows. The Critic sends it back, the Open Loop Agent revises it, then the Critic decides. Decisions are real model output.`
    : `A synthetic calendar event is checked against a real Open Loop stored in Zetaris ("${run.loop_title}"). The Context and Critic decisions are real model output.`
  return { id: run.scenario, label: LABELS[run.scenario] ?? run.scenario, blurb, runs: [run.result], annotations: { inputs: { 0: { title: 'Calendar event', detail } } } }
}

/** Agent Activity over saved real runs. Falls back to the labelled demo traces only if no real run exists. */
export default function LiveAgentActivity() {
  const [demos, setDemos] = useState<DemoRun[] | undefined>()
  const [status, setStatus] = useState<IntegrationStatusResponse['zetaris']>(null)
  useEffect(() => {
    const controller = new AbortController()
    getRuns(controller.signal).then((runs) => setDemos(runs.map(toDemo))).catch(() => undefined)
    getIntegrationStatus(controller.signal).then((value) => setStatus(value.zetaris)).catch(() => undefined)
    return () => controller.abort()
  }, [])
  return <AgentActivity demos={demos} zetaris={status} />
}
