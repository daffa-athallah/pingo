import { useEffect, useRef, useState } from 'react'
import NotificationBanner from './NotificationBanner'
import './notifications.css'

const scenarios = {
  restaurant: { label: 'Restaurant nearby', title: 'That burger place is nearby! 🍔',
    body: "Remember OMB Burger? You saved it a while ago. You’re just around the corner.", item: 'OMB Burger', context: 'Location' },
  calendar: { label: 'Upcoming lunch', title: 'Lunch plans? We have an idea. 🍝',
    body: "You’re meeting Sarah in Carlton next week. Remember that restaurant you saved?", item: 'A restaurant you saved', context: 'Calendar' },
  shopping: { label: 'Shopping nearby', title: 'Something saved is nearby! 🛍️',
    body: "You’re near a store connected to that jacket you bookmarked.", item: 'A jacket you saved', context: 'Location' },
}

/** Example content only. No API imports, fake record IDs, permissions or persistence. */
export default function NotificationVisualPreview() {
  const [scenario, setScenario] = useState<keyof typeof scenarios>('restaurant')
  const [surface, setSurface] = useState<'in-app' | 'iphone'>('iphone')
  const [shown, setShown] = useState(false)
  const [detail, setDetail] = useState(false)
  const [animation, setAnimation] = useState(0)
  const detailRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (detail) { detailRef.current?.focus({ preventScroll: true }); detailRef.current?.scrollIntoView({ block: 'nearest' }) }
  }, [detail])
  const example = scenarios[scenario]
  function close() { setShown(false); setDetail(false) }
  return <section className="notification-visual-preview" aria-labelledby="notification-preview-title">
    <header><h2 id="notification-preview-title">Notification Preview</h2><p>Try a little ping. These are examples, with no agent calls or changes to your saved things.</p></header>
    <label className="notification-preview-select">Scenario<select value={scenario} onChange={event => { close(); setScenario(event.target.value as keyof typeof scenarios) }}>
      {Object.entries(scenarios).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}
    </select></label>
    <fieldset className="notification-preview-surfaces"><legend>Preview style</legend>
      <label><input type="radio" name="preview-surface" checked={surface === 'in-app'} onChange={() => { close(); setSurface('in-app') }} />Preview in-app notification</label>
      <label><input type="radio" name="preview-surface" checked={surface === 'iphone'} onChange={() => { close(); setSurface('iphone') }} />Preview iPhone-style notification</label>
    </fieldset>
    <div className="context-actions"><button type="button" className="context-primary" onClick={() => { setShown(true); setDetail(false); setAnimation(value => value + 1) }}>Preview notification</button>
      {(shown || detail) && <button type="button" className="context-secondary" onClick={close}>Close preview</button>}</div>
    <p className="notification-preview-disclosure">Visual examples only. The iPhone style is a web simulation; iOS controls actual system notifications.</p>
    {shown && <aside className="pingo-notices pingo-example-notices" aria-label="Example notification preview" aria-live="polite">
      <p className="pingo-example-label">Visual preview · {surface === 'iphone' ? 'iPhone style, not iOS' : 'In-app example'}</p>
      <NotificationBanner key={animation} title={example.title} body={example.body} context={`Example · ${example.context}`} surface={surface}
        onOpen={() => { setShown(false); setDetail(true) }} onDismiss={close} />
    </aside>}
    {detail && <section ref={detailRef} className="notification-example-detail" aria-label="Example saved item" tabIndex={-1}>
      <h3>{example.item}</h3><p>This is example content for checking the design. It is not linked to a real saved item, screenshot or agent decision.</p>
      <p>Real pings open Why now?, your saved intention and its original screenshots. Use Real agent evaluation to test that connection.</p>
      <button type="button" className="context-secondary" onClick={close}>Close preview</button>
    </section>}
  </section>
}
