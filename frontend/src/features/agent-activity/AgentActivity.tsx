import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import EventInspector from './EventInspector'
import ExecutionGraph from './ExecutionGraph'
import RunSummary from './RunSummary'
import SystemMap from './SystemMap'
import { timelineKeyForMapNode } from './mapModel'
import type { MapNodeId } from './mapModel'
import { buildTimeline } from './traceAdapter'
import { demoRuns } from './demoRuns'
import type { Annotations, DemoRun, RunResult } from './types'
import './agent-activity.css'

const ARCHITECTURE = [
  ['Evidence', 'perception'], ['Open Loop', 'intention'], ['Context', 'relevance'], ['Critic', 'judgment'], ['Zetaris', 'shared state'], ['Nightshift', 'model routing'],
]

interface Props {
  /** Live data. When omitted the page shows the local demo traces. */
  runs?: RunResult[]
  annotations?: Annotations
  /** True while events are still arriving (e.g. from a stream). New steps animate in without restarting the playback. */
  live?: boolean
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return undefined
    const update = () => setReduced(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return reduced
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia?.(query).matches)
  useEffect(() => {
    const list = window.matchMedia?.(query)
    if (!list) return undefined
    const update = () => setMatches(list.matches)
    update()
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [query])
  return matches
}

const STEP_MS: Record<string, number> = { input: 260, state: 260, event: 900, result: 800 }

export default function AgentActivity({ runs, annotations, live = false }: Props) {
  const reduced = usePrefersReducedMotion()
  const [params, setParams] = useSearchParams()
  const demoId = params.get('demo') ?? demoRuns[0].id
  const setDemoId = (id: string) => setParams({ demo: id }, { replace: true })
  const demo: DemoRun | undefined = runs ? undefined : demoRuns.find((d) => d.id === demoId) ?? demoRuns[0]
  const timeline = useMemo(() => buildTimeline(runs ?? demo!.runs, annotations ?? demo?.annotations), [runs, annotations, demo])
  const total = timeline.nodes.length
  const [visibleCount, setVisibleCount] = useState(reduced ? total : 1)
  const [playing, setPlaying] = useState(!reduced)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const inspectorRef = useRef<HTMLDivElement>(null)
  const wide = useMediaQuery('(min-width: 760px)')
  const [chosenView, setChosenView] = useState<'map' | 'trace'>('map')
  const view = wide ? chosenView : 'trace'

  const restart = useCallback(() => {
    setSelectedKey(null)
    if (reduced) { setVisibleCount(total); setPlaying(false); return }
    setVisibleCount(1)
    setPlaying(true)
  }, [reduced, total])

  useEffect(() => {
    if (live) setPlaying(true)
    else restart()
  }, [timeline, restart, live])

  useEffect(() => {
    if (!playing) return undefined
    if (visibleCount >= total) { setPlaying(false); return undefined }
    const delay = STEP_MS[timeline.nodes[visibleCount]?.kind ?? 'event']
    const timer = window.setTimeout(() => setVisibleCount((n) => n + 1), delay)
    return () => window.clearTimeout(timer)
  }, [playing, visibleCount, total, timeline])

  const finish = () => { setPlaying(false); setVisibleCount(total) }
  const lastEvent = [...timeline.nodes.slice(0, visibleCount)].reverse().find((n) => n.kind === 'event') ?? timeline.nodes[Math.min(visibleCount, total) - 1]
  // Once playback finishes, open the most instructive step (a Critic sending work back) before falling back to the result.
  const turningPoint = timeline.nodes.find((n) => n.event && ['REQUEST_REVISION', 'VERIFY_CONTEXT'].includes(n.event.action))
  const selected = timeline.nodes.find((n) => n.key === selectedKey && timeline.nodes.indexOf(n) < visibleCount)
    ?? (visibleCount >= total ? turningPoint ?? lastEvent : lastEvent)

  const select = (key: string) => {
    setSelectedKey(key)
    setPlaying(false)
    if (window.matchMedia?.('(max-width: 999px)').matches) inspectorRef.current?.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' })
  }

  const selectMapNode = (id: MapNodeId) => {
    const key = timelineKeyForMapNode(timeline, visibleCount, id)
    if (key) select(key)
  }
  const focusKey = playing ? timeline.nodes[visibleCount - 1]?.key ?? null : selected?.key ?? null
  const animateFocus = playing || selectedKey !== null
  const done = visibleCount >= total
  return (
    <div className="aa-page">
      <header className="aa-header">
        <div className="aa-title-row">
          <h1>Agent Activity</h1>
          {demo ? <span className="aa-demo-badge">Demo trace</span> : <span className="aa-demo-badge is-live">{live ? 'Live' : 'Run trace'}</span>}
        </div>
        <p className="aa-tagline">No single model call decides what the user sees.</p>
        <ul className="aa-architecture" aria-label="Architecture">
          {ARCHITECTURE.map(([name, role]) => <li key={name}><strong>{name}</strong> {role}</li>)}
        </ul>
      </header>

      {demo ? (
        <div className="aa-demos" role="tablist" aria-label="Demo runs">
          {demoRuns.map((d) => (
            <button key={d.id} type="button" role="tab" aria-selected={d.id === demo.id} className={d.id === demo.id ? 'is-active' : ''} onClick={() => setDemoId(d.id)}>{d.label}</button>
          ))}
        </div>
      ) : null}
      {demo ? <p className="aa-blurb">{demo.blurb}</p> : null}

      <div className="aa-toolbar">
        <RunSummary timeline={timeline} />
        {wide ? (
          <div className="aa-view" role="tablist" aria-label="View">
            <button type="button" role="tab" aria-selected={view === 'map'} className={view === 'map' ? 'is-active' : ''} onClick={() => setChosenView('map')}>System map</button>
            <button type="button" role="tab" aria-selected={view === 'trace'} className={view === 'trace' ? 'is-active' : ''} onClick={() => setChosenView('trace')}>Trace</button>
          </div>
        ) : null}
        {!reduced ? (
          <div className="aa-controls">
            {!done ? <button type="button" onClick={finish}>Skip</button> : null}
            <button type="button" onClick={restart}>Replay</button>
          </div>
        ) : null}
      </div>

      <div className={`aa-body${view === 'map' ? ' is-map' : ''}`}>
        {view === 'map' ? (
          <SystemMap timeline={timeline} visibleCount={visibleCount} focusKey={focusKey} animateFocus={animateFocus} onSelectNode={selectMapNode} />
        ) : (
          <ExecutionGraph timeline={timeline} visibleCount={visibleCount} selectedKey={selected?.key ?? null} onSelect={select} animate={!reduced} playing={playing} />
        )}
        <div className="aa-side" ref={inspectorRef}>
          <EventInspector node={selected ?? null} demo={Boolean(demo)} />
        </div>
      </div>

      <footer className="aa-footer">
        <p>No Recall without evidence. No interruption without context.</p>
        <p>Zetaris integration is a placeholder in this view. Steps shown as shared state are not claimed as Zetaris queries.</p>
      </footer>
    </div>
  )
}
