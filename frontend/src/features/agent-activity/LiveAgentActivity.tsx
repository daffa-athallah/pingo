import { useEffect, useState } from 'react'
import { getIntegrationStatus } from '../../services/api'
import type { IntegrationStatusResponse } from '../../services/api'
import { getHealth, getRunRecords } from '../../services/runsApi'
import type { Health, RunRecord } from '../../services/runsApi'
import AgentActivity from './AgentActivity'
import type { DemoRun } from './types'

const CURATED: Record<string, string> = { A_relevant: 'Relevant context', B_restraint: 'Restraint', revision: 'Revision' }

function clock(timestamp: string | null) {
  const d = timestamp ? new Date(timestamp) : null
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
}

function toDemo(run: RunRecord): DemoRun {
  const common = { id: run.run_id, provenance: run.provenance, status: run.status, workspace: run.workspace, runs: [run.result] }
  if (run.kind === 'screenshot_upload') {
    return { ...common, label: `Upload ${clock(run.started_at)}`.trim(), annotations: {},
      blurb: 'A new screenshot goes through the Evidence Agent, is stored, and the Open Loop Agent decides what it means. Steps appear as they happen.' }
  }
  if (run.kind === 'scripted_sample') {
    return { ...common, label: 'Scripted sample', annotations: {},
      blurb: 'Answers scripted by the credential-free sample fixture. The agent code runs, but no model was called.' }
  }
  const event = run.context_event ?? run.context_events?.find((e) => e.evaluated !== false)
  const place = [event?.location_name, event?.city].filter(Boolean).join(', ')
  const input = `${event?.title ?? 'Calendar event'}${place ? ` · ${place}` : ''}${run.synthetic_inputs ? ' (synthetic test input)' : ''}`
  if (run.kind === 'revision_fixture') {
    return { ...common, label: CURATED.revision, annotations: { inputs: { 0: { title: 'Calendar event', detail: 'Synthetic over-specific loop (test fixture) with a synthetic calendar event' } } },
      blurb: `Controlled fixture: the loop "${run.original_title}" says more than the evidence shows. The Critic sends it back, the Open Loop Agent revises it, then the Critic decides. Decisions are real model output.` }
  }
  return { ...common, label: CURATED[run.label] ?? (run.kind === 'context_evaluate' ? `Context ${clock(run.started_at)}`.trim() : run.label),
    annotations: { inputs: { 0: { title: 'Calendar event', detail: input } } },
    blurb: run.loop_title ? `A synthetic calendar event is checked against a real Open Loop ("${run.loop_title}"). The Context and Critic decisions are real model output.`
      : 'An event is checked against the saved Open Loops by the Context Agent, then judged by the Critic.' }
}

/** Agent Activity over the runs of the active workspace. Falls back to labelled hand-written illustrations only if there is no run at all. */
export default function LiveAgentActivity() {
  const [runs, setRuns] = useState<RunRecord[] | undefined>()
  const [status, setStatus] = useState<IntegrationStatusResponse['zetaris']>(null)
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(setHealth).catch(() => undefined)
    getIntegrationStatus(controller.signal).then((value) => setStatus(value.zetaris)).catch(() => undefined)
    return () => controller.abort()
  }, [])

  const anyRunning = runs?.some((run) => run.status === 'running') ?? false
  useEffect(() => {
    const controller = new AbortController()
    const load = () => getRunRecords(controller.signal).then(setRuns).catch(() => undefined)
    load()
    // While a run is executing its steps arrive one by one: refresh every second until it finishes.
    const timer = anyRunning ? window.setInterval(load, 1000) : undefined
    return () => { controller.abort(); if (timer) window.clearInterval(timer) }
  }, [anyRunning])

  const demos = runs?.map(toDemo)
  const workspaceNote = health?.mode === 'demo'
    ? 'Demo workspace: an in-memory copy of the Zetaris history. Nothing here is written to Zetaris, and the workspace can be reset.'
    : health?.mode === 'sample' ? 'Offline sample: no Zetaris, no models. Anything labelled scripted was answered by a fixture.' : undefined
  return <AgentActivity demos={demos} zetaris={status} workspaceNote={workspaceNote} />
}
