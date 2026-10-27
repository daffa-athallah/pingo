// Real browser interactions; backend contract responses are explicit offline fixtures.
// No model or database request is allowed through this tab's interception.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
const output = new URL('../../artifacts/ui/notification-scenarios/', import.meta.url)
await mkdir(output, { recursive: true })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
async function connect(url) {
  const ws = new WebSocket(url)
  await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }))
  let seq = 0
  const tasks = new Map(), listeners = []
  ws.addEventListener('message', event => {
    const data = JSON.parse(event.data)
    if (data.id) { const task = tasks.get(data.id); tasks.delete(data.id); if (task) data.error ? task.reject(data.error) : task.resolve(data.result) }
    else for (const fn of listeners) fn(data)
  })
  return { ws, listeners, send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++seq, timer = setTimeout(() => { tasks.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 25000)
      tasks.set(id, { resolve: value => { clearTimeout(timer); resolve(value) }, reject: error => { clearTimeout(timer); reject(error) } })
      ws.send(JSON.stringify({ id, method, params }))
    })
  } }
}
const version = await (await fetch('http://127.0.0.1:9333/json/version')).json()
const browser = await connect(version.webSocketDebuggerUrl)
const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank' })
const tabs = await (await fetch('http://127.0.0.1:9333/json/list')).json()
const client = await connect(tabs.find(tab => tab.id === targetId).webSocketDebuggerUrl)
const evaluate = async expression => (await client.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value
async function until(expression) {
  for (let n=0;n<100;n++) { if (await evaluate(expression)) return; await pause(100) }
  throw new Error(`Timed out: ${expression}`)
}
async function navigate(route) {
  await client.send('Page.navigate', { url: 'http://127.0.0.1:5176' + route })
  await pause(200)
  await until(`!!document.querySelector('.context-test-modes')`)
}
async function screenshot(name) {
  if (process.env.PINGO_SKIP_SCREENSHOTS === 'true') return
  await evaluate('document.fonts.ready.then(()=>true)'); await pause(350)
  const capture = await client.send('Page.captureScreenshot',{format:'png'})
  await writeFile(new URL(`${name}.png`,output),Buffer.from(capture.data,'base64'))
}
async function setValue(selector, value) {
  await evaluate(`(()=>{const input=${selector};const proto=input instanceof HTMLSelectElement?HTMLSelectElement.prototype:input instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event(input instanceof HTMLSelectElement?'change':'input',{bubbles:true}))})()`)
}
const api = [], errors = [], metrics = []
let fixtureMode = 'offline', notification = null
let failDismiss = false
const place = { entity_id: 'ent_ui_test', name: 'Explicit restaurant fixture', domain: 'food', metadata: { latitude: '-37.8', longitude: '144.967', location_verified: 'true', location_source: 'explicit_test_fixture' } }
const loop = { loop_id: 'loop_ui_test', title: 'Interested in explicit restaurant fixture', domain: 'food', status: 'ACTIVE', confidence: .8, location: 'Test location', entities: [{ entity_id: place.entity_id, name: place.name }], screenshots: [{ evidence_id: 'ev_ui_test', summary: 'Explicit UI fixture', timestamp: '2026-10-25T00:00:00Z', image_url: '/evidence/ev_ui_test/image' }] }
client.listeners.push(async event => {
  if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.text)
  if (event.method !== 'Fetch.requestPaused') return
  const { requestId, request } = event.params
  const path = new URL(request.url).pathname.replace(/^\/backend/,'')
  api.push({ path, method: request.method, body: request.postData ? JSON.parse(request.postData) : null })
  let code = fixtureMode === 'offline' ? 503 : 200, body = []
  if (path === '/api/check-ins') body = { questions: [] }
  else if (path === '/context-simulator/places') body = [place, { ...place, entity_id: 'ent_missing', name: 'Unlocated fixture', metadata: {} }]
  else if (path === '/open-loops') body = [loop]
  else if (path === '/context-simulator/evaluate') {
    const submitted = JSON.parse(request.postData)
    const surface = fixtureMode === 'surface'
    notification = surface ? { notification_id: 'notice_ui_test', loop_id: loop.loop_id, created_at: new Date().toISOString(), payload: {
      title: loop.title, message: 'Explicit approved UI fixture.', reason: 'Scripted fixture for the notification contract test.',
      run_id: 'run_ui_test', sources: ['SIMULATED'], trigger_types: [submitted.events[0].type], delivery_status: 'APPROVED', read: false, dismissed: false, feedback: null,
      entities: loop.entities, evidence: [{ evidence_id: 'ev_ui_test', summary: 'Explicit fixture evidence', image_url: null }],
    } } : null
    body = { evaluation_id: 'eval_ui_test', state: 'COMPLETED', source: ['SIMULATED'], submitted_context: submitted.events,
      candidates: [{ loop_id: loop.loop_id, title: loop.title, eligible: true, exclusion: null, geography: [] }],
      result: { run_id: 'run_ui_test', final_action: surface ? 'SURFACE' : 'STAY_SILENT', trace_events: [
        { agent: 'CONTEXT', action: 'MATCH', reason: 'Explicit Context fixture.' },
        { agent: 'CRITIC', action: surface ? 'SURFACE' : 'STAY_SILENT', reason: 'Explicit Critic fixture.' },
      ] }, notification_id: notification?.notification_id ?? null, delivery: surface ? 'APPROVED_PENDING_DELIVERY' : 'NOT_APPROVED' }
  } else if (path === '/notifications') body = notification && !notification.payload.dismissed ? [notification] : []
  else if (path.startsWith('/notifications/')) {
    if (request.method === 'POST' && notification) {
      const action = JSON.parse(request.postData).action
      if (action === 'DELIVERED') notification.payload.delivery_status = 'DELIVERED'
      if (action === 'READ') notification.payload.read = true
      if (action === 'DISMISS') {
        if (failDismiss) code = 503
        else notification.payload.dismissed = true
      }
    }
    body = notification
  } else if (path.startsWith('/evidence/')) { code = 404; body = {} }
  await client.send('Fetch.fulfillRequest',{requestId,responseCode:code,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')}).catch(error=>{
    if (!/Invalid InterceptionId/i.test(error.message||'')) errors.push(JSON.stringify(error))
  })
})
try {
  await client.send('Page.enable'); await client.send('Runtime.enable')
  await client.send('Fetch.enable',{patterns:[{urlPattern:'*/backend/*'}]})
  for (const width of [375,390,430]) {
    await client.send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true})
    await navigate('/context-simulator')
    await until(`!!document.querySelector('.notification-preview-select select')`)
    await pause(200)
    const before = api.length
    for (const scenario of ['restaurant','calendar','shopping']) {
      await setValue(`document.querySelector('.notification-preview-select select')`,scenario)
      await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent==='Preview notification').click()`)
      await until(`!!document.querySelector('.pingo-example-notices .pingo-notice')`)
      await until(`document.querySelector('.pingo-notice-icon').naturalWidth>0`)
      const bounds = await evaluate(`({right:document.querySelector('.pingo-notice-wrap').getBoundingClientRect().right,bottom:document.querySelector('.pingo-notice-wrap').getBoundingClientRect().bottom,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,icon:document.querySelector('.pingo-notice-icon').naturalWidth,title:document.querySelector('.pingo-notice strong').textContent})`)
      assert.equal(bounds.width,bounds.scrollWidth)
      assert.ok(bounds.right<=width && bounds.bottom<844-80)
      assert.ok(bounds.icon>0)
      await screenshot(`${scenario}-iphone-${width}`)
      metrics.push({scenario,width,...bounds})
      await evaluate(`document.querySelector('.pingo-notice-dismiss').click()`)
      assert.equal(await evaluate(`!!document.querySelector('.pingo-example-notices')`),false)
    }
    assert.equal(api.length,before,'Visual previews must not issue API requests')
  }
  await client.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  await evaluate(`document.querySelector('input[name=preview-surface]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent==='Preview notification').click()`)
  await screenshot('shopping-in-app-390')
  await evaluate(`document.querySelector('.pingo-notice').click()`)
  await until(`!!document.querySelector('.notification-example-detail')`)
  assert.equal(api.filter(item=>item.method==='POST').length,0)
  fixtureMode = 'surface'
  await evaluate(`[...document.querySelectorAll('.context-test-modes button')].find(button=>button.textContent==='Real agent evaluation').click()`)
  await until(`!!document.querySelector('.context-presets')`)
  await evaluate(`[...document.querySelectorAll('.context-presets button')].find(button=>button.textContent==='Load saved locations').click()`)
  await until(`!!document.querySelector('.context-presets select')`)
  await evaluate(`[...document.querySelectorAll('.context-presets button')].find(button=>button.textContent==='Near saved restaurant').click()`)
  await evaluate(`document.querySelector('.context-form button[type=submit]').click()`)
  await evaluate(`[...document.querySelectorAll('.context-queue button')].find(button=>button.textContent==='Run agent evaluation').click()`)
  await until(`!!document.querySelector('.pingo-notice') && !!document.querySelector('.context-result')`)
  const submission = api.find(item=>item.path==='/context-simulator/evaluate').body
  assert.equal(submission.events[0].source,'SIMULATED')
  assert.equal(submission.events[0].location.accuracy_meters,20)
  assert.ok(submission.events[0].location.latitude>-37.8)
  assert.equal(submission.events.length,1)
  await screenshot('contract-surface-fixture-390')
  assert.equal(await evaluate(`document.querySelector('.pingo-notice').getAttribute('href')`),'/recalls/notice_ui_test')
  await evaluate(`document.querySelector('.pingo-notice').click()`)
  await until(`!!document.querySelector('.pingo-why-now')`)
  assert.equal(await evaluate(`document.querySelector('.pingo-recall-detail .context-primary').getAttribute('href')`),'/entity/loop_ui_test')
  assert.match(await evaluate(`document.querySelector('.pingo-evidence').textContent`),/fixture evidence/)
  notification = { ...notification, notification_id: 'notice_dismiss_ui_test', payload: { ...notification.payload, read: false, dismissed: false } }
  await navigate('/context-simulator?mode=agents')
  await until(`!!document.querySelector('.pingo-notice-dismiss')`)
  failDismiss = true
  await evaluate(`document.querySelector('.pingo-notice-dismiss').click()`)
  await until(`!!document.querySelector('.pingo-dismiss-error')`)
  assert.equal(await evaluate(`!!document.querySelector('.pingo-notice')`),true,'Failed dismissal must keep the real banner available')
  const dismissCount = api.filter(item=>item.body?.action==='DISMISS').length
  failDismiss = false
  await evaluate(`(()=>{const button=document.querySelector('.pingo-notice-dismiss');button.click();button.click()})()`)
  await until(`!document.querySelector('.pingo-notice')`)
  assert.equal(api.filter(item=>item.body?.action==='DISMISS').length,dismissCount+1,'Duplicate dismissal clicks submit once')
  fixtureMode = 'silent'; notification = null
  await navigate('/context-simulator?mode=agents')
  await evaluate(`[...document.querySelectorAll('.context-tabs button')].find(button=>button.textContent==='Calendar').click()`)
  const labelInput = prefix => `[...document.querySelectorAll('.context-form label')].find(label=>label.textContent.startsWith(${JSON.stringify(prefix)})).querySelector('input,textarea')`
  for (const [prefix,value] of [['Event title','Lunch with Sarah'],['Start','2026-11-03T12:30'],['End','2026-11-03T14:00'],['City','Melbourne'],['Location label','Carlton'],['Description','Explicit offline test event']]) await setValue(labelInput(prefix),value)
  await evaluate(`document.querySelector('.context-form button[type=submit]').click()`)
  await evaluate(`[...document.querySelectorAll('.context-queue button')].find(button=>button.textContent==='Run agent evaluation').click()`)
  await until(`document.querySelector('.context-result h2')?.textContent==='STAY_SILENT'`)
  assert.equal(await evaluate(`!!document.querySelector('.pingo-notice')`),false)
  const calendar = api.filter(item=>item.path==='/context-simulator/evaluate').at(-1).body.events[0]
  assert.equal(calendar.type,'CALENDAR'); assert.equal(calendar.location.city,'Melbourne'); assert.equal(calendar.title,'Lunch with Sarah')
  const evaluationCount = api.filter(item=>item.path==='/context-simulator/evaluate').length
  await evaluate(`window.dispatchEvent(new Event('pingo-notifications-changed'))`); await pause(200)
  assert.equal(api.filter(item=>item.path==='/context-simulator/evaluate').length,evaluationCount,'Notification refresh must never evaluate context')
  await screenshot('contract-stay-silent-fixture-390')
  assert.deepEqual(errors,[])
  const result={label:'Browser UI and contract tests only; all backend requests intercepted',visualPreviews:metrics.length,metrics,evaluationRequests:evaluationCount,errors,previewWorksWith503:true}
  await writeFile(new URL('browser-results.json',output),JSON.stringify(result,null,2))
  console.log(JSON.stringify(result,null,2))
} finally {
  client.ws.close(); await browser.send('Target.closeTarget',{targetId}); browser.ws.close()
}
