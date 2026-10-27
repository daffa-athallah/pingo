import { useEffect, useRef, useState } from 'react'
import { evaluateContext, getContextEntities, getOpenLoopViews } from '../../services/api'
import { getHealth } from '../../services/runsApi'
import type { ContextInput } from '../../services/api'
import { contextPlaces } from '../../pages/context/contextPresets'
import type { VerifiedPlace } from '../../pages/context/contextPresets'
import './nearby.css'

// Always aware while the app is open: no button. Getting this close (distance plus GPS uncertainty) wakes the agents; after leaving and coming back
// it wakes them again. The backend decides whether to speak (and applies its own cooldown); a web page cannot watch while it is in the background.
const ENTER_METERS = 1000
const EXIT_METERS = 1300
const PLACE_REFRESH_MS = 60_000

function metres(aLat: number, aLon: number, bLat: number, bLon: number) {
  const r = (v: number) => (v * Math.PI) / 180
  const h = Math.sin(r(bLat - aLat) / 2) ** 2 + Math.cos(r(aLat)) * Math.cos(r(bLat)) * Math.sin(r(bLon - aLon) / 2) ** 2
  return 6371008.8 * 2 * Math.asin(Math.min(1, Math.sqrt(h)))
}
type Wake = { release: () => Promise<void> }

export default function NearbyAware() {
  const [, setPlaces] = useState<VerifiedPlace[]>([])
  const [status, setStatus] = useState('')
  const [enabled, setEnabled] = useState(false)  // the offline sample has no location to watch, so it never asks a judge for theirs
  const placesRef = useRef<VerifiedPlace[]>([])
  const inside = useRef(new Set<string>())  // places the person is currently within reach of; each re-arms when they leave it
  const busy = useRef(false)
  const wake = useRef<Wake | null>(null)

  useEffect(() => {
    getHealth().then((h) => setEnabled(!(h.mode === 'sample' && !h.live_models))).catch(() => setEnabled(false))
  }, [])

  useEffect(() => {
    let alive = true
    const load = () => Promise.all([getContextEntities(), getOpenLoopViews()]).then(([entities, loops]) => {
      if (!alive) return
      const data = contextPlaces(entities, loops)
      placesRef.current = data.places; setPlaces(data.places)
    }).catch(() => undefined)
    void load()
    const timer = window.setInterval(() => void load(), PLACE_REFRESH_MS)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!enabled) return undefined
    if (!window.isSecureContext || !navigator.geolocation) { setStatus('Location needs the secure (https) address'); return undefined }
    setStatus('Allow location so Pingo can notice when you are near a saved place')
    async function ask(latitude: number, longitude: number, accuracy: number, at: number, name: string, distance: number) {
      if (busy.current) return
      busy.current = true; setStatus(`Near ${name} (${Math.round(distance)} m): asking the agents…`)
      try {
        const iso = new Date(at).toISOString()
        const event: ContextInput = { context_id: `ctx_${crypto.randomUUID()}`, source: 'BROWSER', type: 'LOCATION', timestamp: iso,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, location: { latitude, longitude, accuracy_meters: accuracy } }
        const response = await evaluateContext([event], iso)
        window.dispatchEvent(new Event('pingo-notifications-changed'))
        setStatus(response.notification_id ? `Pinged you about ${name}` : `Checked ${name}: staying quiet`)
      } catch { setStatus('Could not check just now') }
      finally { busy.current = false }
    }
    const id = navigator.geolocation.watchPosition((pos) => {
      const { latitude, longitude, accuracy } = pos.coords
      const ranked = placesRef.current.map((p) => ({ p, d: metres(latitude, longitude, p.latitude, p.longitude) })).sort((x, y) => x.d - y.d)
      const near = ranked[0]
      if (!near) { setStatus('Aware of where you are · no saved place has a map location yet'); return }
      const entered = ranked.filter(({ p, d }) => !inside.current.has(p.entityId) && d + accuracy <= ENTER_METERS)
      for (const { p, d } of ranked) if (inside.current.has(p.entityId) && d > EXIT_METERS) inside.current.delete(p.entityId)
      if (entered.length) {
        entered.forEach(({ p }) => inside.current.add(p.entityId))
        void ask(latitude, longitude, accuracy, pos.timestamp, entered[0].p.name, entered[0].d)  // one check covers every saved place near this point
      } else setStatus(`Watching ${ranked.length} place${ranked.length === 1 ? '' : 's'} · nearest ${near.p.name}, ${Math.round(near.d)} m`)
    }, (e) => setStatus(e.code === 1 ? 'Location is off for Pingo. Turn it on in Settings → Privacy → Location Services' : 'Looking for your location…'), { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 })
    // Keep the screen awake once the person touches the app (a browser needs a gesture for this).
    const keepAwake = async () => {
      try { wake.current = await (navigator as unknown as { wakeLock?: { request: (t: 'screen') => Promise<Wake> } }).wakeLock?.request('screen') ?? null } catch { /* optional */ }
    }
    window.addEventListener('pointerdown', keepAwake, { once: true })
    const reacquire = () => { if (document.visibilityState === 'visible' && !wake.current) void keepAwake() }
    document.addEventListener('visibilitychange', reacquire)
    return () => {
      navigator.geolocation.clearWatch(id); window.removeEventListener('pointerdown', keepAwake); document.removeEventListener('visibilitychange', reacquire)
      void wake.current?.release().catch(() => undefined); wake.current = null; inside.current.clear()
    }
  }, [enabled])

  if (!enabled) return null
  return <div className="nearby-chip" role="status"><span className="nearby-dot" />{status || 'Pingo is aware of where you are'}</div>
}
