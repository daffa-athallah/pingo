import { useEffect, useRef, useState } from 'react'
import { evaluateContext, getContextEntities, getOpenLoopViews } from '../../services/api'
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
  const [places, setPlaces] = useState<VerifiedPlace[]>([])
  const [status, setStatus] = useState('')
  const placesRef = useRef<VerifiedPlace[]>([])
  const inside = useRef(false)
  const busy = useRef(false)
  const wake = useRef<Wake | null>(null)

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

  const watching = places.length > 0
  useEffect(() => {
    if (!watching || !window.isSecureContext || !navigator.geolocation) return undefined
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
      const ranked = placesRef.current.map((p) => ({ p, d: metres(latitude, longitude, p.latitude, p.longitude) })).sort((a, b) => a.d - b.d)
      const near = ranked[0]
      if (!near) return
      if (!inside.current && near.d + accuracy <= ENTER_METERS) { inside.current = true; void ask(latitude, longitude, accuracy, pos.timestamp, near.p.name, near.d) }
      else if (inside.current && near.d > EXIT_METERS) { inside.current = false; setStatus(`Watching · ${Math.round(near.d)} m from ${near.p.name}`) }
      else if (!inside.current) setStatus(`Watching · ${Math.round(near.d)} m from ${near.p.name}`)
    }, (e) => setStatus(e.code === 1 ? 'Location is off for Pingo' : 'Looking for your location…'), { enableHighAccuracy: true, maximumAge: 0, timeout: 30000 })
    // Keep the screen awake once the person touches the app (a browser needs a gesture for this).
    const keepAwake = async () => {
      try { wake.current = await (navigator as unknown as { wakeLock?: { request: (t: 'screen') => Promise<Wake> } }).wakeLock?.request('screen') ?? null } catch { /* optional */ }
    }
    window.addEventListener('pointerdown', keepAwake, { once: true })
    const reacquire = () => { if (document.visibilityState === 'visible' && !wake.current) void keepAwake() }
    document.addEventListener('visibilitychange', reacquire)
    return () => {
      navigator.geolocation.clearWatch(id); window.removeEventListener('pointerdown', keepAwake); document.removeEventListener('visibilitychange', reacquire)
      void wake.current?.release().catch(() => undefined); wake.current = null; inside.current = false
    }
  }, [watching])

  if (!watching) return null
  return <div className="nearby-chip" role="status"><span className="nearby-dot" />{status || 'Pingo is aware of where you are'}</div>
}
