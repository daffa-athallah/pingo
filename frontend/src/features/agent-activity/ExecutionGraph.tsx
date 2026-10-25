import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import EventNode from './EventNode'
import ResultNode from './ResultNode'
import type { Timeline, TimelineEdge } from './traceAdapter'

interface Props {
  timeline: Timeline
  visibleCount: number
  selectedKey: string | null
  onSelect: (key: string) => void
  animate: boolean
  playing: boolean
}

interface Geometry { edge: TimelineEdge; d: string; labelX: number; labelY: number }

const ANCHOR = 34

function elbow(x1: number, y1: number, x2: number, y2: number, radius = 12): string {
  if (Math.abs(x1 - x2) < 1) return `M${x1} ${y1} V${y2}`
  const ym = (y1 + y2) / 2
  const dir = x2 > x1 ? 1 : -1
  const r = Math.max(2, Math.min(radius, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 4))
  return `M${x1} ${y1} V${ym - r} Q${x1} ${ym} ${x1 + dir * r} ${ym} H${x2 - dir * r} Q${x2} ${ym} ${x2} ${ym + r} V${y2}`
}

export default function ExecutionGraph({ timeline, visibleCount, selectedKey, onSelect, animate, playing }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>())
  const [geometry, setGeometry] = useState<Geometry[]>([])
  const [size, setSize] = useState({ width: 0, height: 0 })
  const index = new Map(timeline.nodes.map((node, i) => [node.key, i]))

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const next: Geometry[] = []
    for (const edge of timeline.edges) {
      const a = nodeRefs.current.get(edge.from)
      const b = nodeRefs.current.get(edge.to)
      if (!a || !b) continue
      const x1 = a.offsetLeft + ANCHOR
      const y1 = a.offsetTop + a.offsetHeight
      const x2 = b.offsetLeft + ANCHOR
      const y2 = b.offsetTop - 3
      next.push({ edge, d: elbow(x1, y1, x2, y2), labelX: Math.max(x1, x2) + 16, labelY: (y1 + y2) / 2 })
    }
    setGeometry(next)
    setSize({ width: container.offsetWidth, height: container.offsetHeight })
  }, [timeline])

  useLayoutEffect(() => {
    measure()
    const container = containerRef.current
    if (!container || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    nodeRefs.current.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [measure])

  useEffect(() => {
    if (document.fonts?.ready) void document.fonts.ready.then(measure)
  }, [measure])

  const activeIndex = playing ? visibleCount - 1 : -1

  return (
    <div className="aa-graph" ref={containerRef}>
      <svg className="aa-edges" width={size.width} height={size.height} aria-hidden="true">
        <defs>
          {(['neutral', 'accent'] as const).map((tone) => (
            <marker key={tone} id={`aa-arrow-${tone}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M1 1.5 8.5 5 1 8.5Z" className={`aa-arrow aa-arrow-${tone}`} />
            </marker>
          ))}
        </defs>
        {geometry.map(({ edge, d }) => {
          const shown = (index.get(edge.to) ?? 0) < visibleCount
          const accent = edge.kind !== 'forward' && !edge.to.endsWith('-result')
          return (
            <Fragment key={`${edge.from}>${edge.to}`}>
              <path d={d} className={`aa-edge aa-edge-${edge.kind}${shown ? ' is-visible' : ''}${accent ? ' is-accent' : ''}`}
                markerEnd={`url(#aa-arrow-${accent ? 'accent' : 'neutral'})`} fill="none" />
              {edge.kind === 'return' && shown && animate ? <circle r="4" className="aa-dot" style={{ offsetPath: `path("${d}")` }} /> : null}
            </Fragment>
          )
        })}
      </svg>

      {timeline.nodes.map((node, i) => {
        const visible = i < visibleCount
        const label = geometry.find((g) => g.edge.to === node.key && g.edge.label)
        const result = node.kind === 'result'
        return (
          <Fragment key={node.key}>
            {node.breakBefore ? <div className={`aa-break${visible ? ' is-visible' : ''}`}><span>{node.breakBefore}</span></div> : null}
            <div className={`aa-row${node.lane === 'branch' ? ' is-branch' : ''}`}>
              {result ? (
                <ResultNode node={node} visible={visible} active={i === activeIndex} selected={selectedKey === node.key}
                  onSelect={onSelect} ref={(el) => { if (el) nodeRefs.current.set(node.key, el); else nodeRefs.current.delete(node.key) }} />
              ) : (
                <EventNode node={node} visible={visible} active={i === activeIndex} selected={selectedKey === node.key} onSelect={onSelect}
                  ref={(el) => { if (el) nodeRefs.current.set(node.key, el); else nodeRefs.current.delete(node.key) }} />
              )}
            </div>
            {label && visible ? (
              <span className={`aa-edge-label aa-edge-label-${label.edge.kind}`} style={{ left: label.labelX, top: label.labelY }}>{label.edge.label}</span>
            ) : null}
          </Fragment>
        )
      })}
    </div>
  )
}
