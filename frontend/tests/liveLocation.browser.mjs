// Browser contract test with explicitly simulated GPS and API responses.
// Requires Node 22+, Vite on :5176, and a test Chrome with CDP on :9333.
// This proves UI/input handling, never real GPS, agents, or Zetaris readiness.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'

const base = process.env.PINGO_UI_TEST_URL || 'http://127.0.0.1:5176'
const cdp = process.env.PINGO_CDP_URL || 'http://127.0.0.1:9333'
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const output = new URL('../../artifacts/live-location/', import.meta.url)
await mkdir(output, { recursive: true })
const browser = await (await fetch(`${cdp}/json/version`)).json()

async function connect(url) {
  const socket = new WebSocket(url)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  let id = 0
  const pending = new Map()
  const listeners = []
  socket.addEventListener('close', () => {
    for (const task of pending.values()) task.reject(new Error('CDP connection closed'))
    pending.clear()
  })
  socket.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (data.id) {
      const task = pending.get(data.id)
      pending.delete(data.id)
      if (task) data.error ? task.reject(data.error) : task.resolve(data.result)
    } else for (const listener of listeners) listener(data)
  })
  return {
    socket, listeners,
    send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const key = ++id
        const timer = setTimeout(() => { pending.delete(key); reject(new Error(`CDP timed out: ${method}`)) }, 20000)
        pending.set(key, { resolve: value => { clearTimeout(timer); resolve(value) }, reject: error => { clearTimeout(timer); reject(error) } })
        socket.send(JSON.stringify({ id, method, params }))
      })
    },
  }
}

const browserClient = await connect(browser.webSocketDebuggerUrl)
const results = []
try {
  for (const scenario of ['denied', 'unavailable', 'timeout', 'network', 'failed-safe', 'silent', 'surface']) {
    console.log(`Testing ${scenario}`)
    const { targetId } = await browserClient.send('Target.createTarget', { url: 'about:blank' })
    const tabs = await (await fetch(`${cdp}/json/list`)).json()
    const client = await connect(tabs.find(tab => tab.id === targetId).webSocketDebuggerUrl)
    const evaluate = async expression => (await client.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value
    async function until(expression) {
      for (let n = 0; n < 80; n++) {
        if (await evaluate(expression)) return
        await delay(100)
      }
      throw new Error(`${scenario}: timed out: ${expression}`)
    }
    const requests = []
    const interceptionErrors = []
    let closing = false
    let approved = false
    const notice = {
      notification_id: 'notice_UI_TEST', loop_id: 'loop_UI_TEST', created_at: new Date().toISOString(),
      payload: { title: 'UI test saved place', message: 'Explicit browser test fixture.', reason: 'Simulated approved response for UI testing.',
        run_id: 'run_UI_TEST', sources: ['BROWSER'], trigger_types: ['LOCATION'], delivery_status: 'APPROVED', read: false,
        dismissed: false, feedback: null, entities: [{ entity_id: 'entity_UI_TEST', name: 'UI test place' }],
        evidence: [{ evidence_id: 'evidence_UI_TEST', summary: 'Explicit UI fixture.', image_url: null }] },
    }
    client.listeners.push(async message => {
      if (message.method !== 'Fetch.requestPaused') return
      const { requestId, request } = message.params
      let status = 200, body = []
      const path = new URL(request.url).pathname.replace(/^\/backend/, '')
      if (path === '/context-simulator/evaluate') {
        requests.push(JSON.parse(request.postData))
        if (scenario === 'network') status = 503
        approved = scenario === 'surface'
        body = { evaluation_id: 'eval_UI_TEST', source: ['BROWSER'], state: scenario === 'failed-safe' ? 'FAILED_SAFE' : 'COMPLETED',
          result: { final_action: approved ? 'SURFACE' : scenario === 'failed-safe' ? 'FAILED_SAFE' : 'STAY_SILENT', trace_events: [] },
          notification_id: approved ? notice.notification_id : null, delivery: approved ? 'APPROVED_PENDING_DELIVERY' : 'NOT_APPROVED' }
      } else if (path === '/notifications') body = approved ? [notice] : []
      else if (path.startsWith('/notifications/')) body = notice
      await client.send('Fetch.fulfillRequest', { requestId, responseCode: status,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') }).catch(error => {
          if (!closing && !/Invalid InterceptionId/i.test(error.message || '')) interceptionErrors.push(error.message)
        })
    })
    try {
      await client.send('Page.enable')
      await client.send('Fetch.enable', { patterns: [{ urlPattern: '*/backend/*' }] })
      await client.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
      await client.send('Page.addScriptToEvaluateOnNewDocument', { source: `Object.defineProperty(navigator, 'geolocation', {value: {getCurrentPosition(success, failure) { window.testGpsSuccess = success; window.testGpsFailure = failure; }}})` })
      await client.send('Page.navigate', { url: `${base}/context-simulator?mode=agents` })
      await until(`!!document.querySelector('.context-live button')`)
      await evaluate(`document.querySelector('.context-form button[type=submit]').click()`)
      await evaluate(`document.querySelector('.context-live button').click()`)
      assert.equal(await evaluate(`document.querySelector('.context-live [role=status]').textContent`), 'Requesting your location…')
      if (['denied', 'unavailable', 'timeout'].includes(scenario)) {
        await evaluate(`window.testGpsFailure({code:${scenario === 'denied' ? 1 : scenario === 'timeout' ? 3 : 2}})`)
        await until(`!!document.querySelector('[role=alert]')`)
        assert.equal(requests.length, 0)
        const text = await evaluate(`document.querySelector('[role=alert]').textContent`)
        assert.match(text, scenario === 'denied' ? /denied/ : scenario === 'timeout' ? /timed out/ : /unavailable/)
      } else {
        await evaluate(`window.testGpsSuccess({timestamp:1793149200000,coords:{latitude:-37.8,longitude:144.967,accuracy:12}})`)
        await until(`!document.querySelector('.context-live button').disabled`)
        assert.equal(requests.length, 1)
        assert.equal(requests[0].events.length, 1, 'Staged simulations must be excluded')
        assert.equal(requests[0].events[0].source, 'BROWSER')
        assert.deepEqual(requests[0].events[0].location, { latitude: -37.8, longitude: 144.967, accuracy_meters: 12 })
        assert.equal(requests[0].events[0].timestamp, new Date(1793149200000).toISOString())
        const status = await evaluate(`document.querySelector('.context-live [role=status]').textContent`)
        assert.match(status, scenario === 'surface' ? /relevant ping is available/ : scenario === 'network' ? /could not complete/ : scenario === 'failed-safe' ? /could not finish/ : /Nothing relevant nearby/)
        if (approved) {
          await until(`!!document.querySelector('.pingo-notice')`)
          assert.equal(await evaluate(`document.querySelector('.pingo-notice').getAttribute('href')`), '/recalls/notice_UI_TEST')
          const image = await client.send('Page.captureScreenshot', { format: 'png' })
          await writeFile(new URL('browser-gps-fixture-390.png', output), Buffer.from(image.data, 'base64'))
        }
      }
      assert.deepEqual(interceptionErrors, [])
      results.push({ scenario, passed: true, label: 'Simulated browser GPS/API; no live model or repository calls', evaluation_requests: requests.length })
    } finally {
      closing = true
      client.socket.close()
      await browserClient.send('Target.closeTarget', { targetId })
    }
  }
  await writeFile(new URL('browser-tests.json', output), JSON.stringify(results, null, 2))
  console.log(JSON.stringify(results, null, 2))
} finally {
  browserClient.socket.close()
}
