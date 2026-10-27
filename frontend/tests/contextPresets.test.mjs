import test from 'node:test'
import assert from 'node:assert/strict'
import { contextPlaces, offsetLocation } from '../src/pages/context/contextPresets.ts'
import { notificationCopy, notificationSupport, showSystemNotification } from '../src/features/notifications/systemNotifications.ts'

const entity = { entity_id: 'test_entity', name: 'Explicit test restaurant', domain: 'food', metadata: {
  latitude: '-37.8', longitude: '144.967', location_verified: 'true', location_source: 'explicit_test_fixture',
} }
const loop = { loop_id: 'test_loop', status: 'ACTIVE', entities: [{ entity_id: entity.entity_id }], screenshots: [{ evidence_id: 'test_evidence' }] }

test('location presets require verified coordinates, real active links and evidence', () => {
  const result = contextPlaces([entity], [loop])
  assert.equal(result.places.length, 1)
  assert.deepEqual(result.places[0].loopIds, ['test_loop'])
  assert.deepEqual(result.places[0].evidenceIds, ['test_evidence'])
  for (const metadata of [{}, { ...entity.metadata, location_verified: 'false' }, { ...entity.metadata, latitude: '' }, { ...entity.metadata, longitude: 'Infinity' }, { ...entity.metadata, latitude: '91' }, { ...entity.metadata, location_source: '' }]) {
    const unavailable = contextPlaces([{ ...entity, metadata }], [loop])
    assert.equal(unavailable.places.length, 0)
    assert.match(unavailable.unavailable[0].reason, /Proximity cannot be evaluated/)
  }
  assert.equal(contextPlaces([entity], [{ ...loop, status: 'RESOLVED' }]).places.length, 0)
  assert.equal(contextPlaces([entity], [{ ...loop, screenshots: [] }]).places.length, 0)
  assert.equal(contextPlaces([entity], [{ ...loop, entities: [] }]).places.length, 0)
})

test('shopping proximity requires a verified store association and never establishes inventory', () => {
  const product = { ...entity, domain: 'shopping' }
  assert.equal(contextPlaces([product], [loop]).places.length, 0)
  const associated = contextPlaces([{ ...product, metadata: { ...product.metadata, location_role: 'store', store_name: 'Explicit store fixture' } }], [loop])
  assert.equal(associated.places.length, 1)
  assert.equal('inventory' in associated.places[0], false)
})

test('near and far offsets preserve geographic distances, including crossing a pole', () => {
  function distance(a, b) {
    const radians = value => value * Math.PI / 180
    const h = Math.sin(radians(b.latitude-a.latitude)/2)**2 + Math.cos(radians(a.latitude))*Math.cos(radians(b.latitude))*Math.sin(radians(b.longitude-a.longitude)/2)**2
    return 2 * 6371008.8 * Math.asin(Math.sqrt(h))
  }
  for (const origin of [{ latitude: -37.8, longitude: 144.967 }, { latitude: 89.999, longitude: 170 }]) {
    for (const meters of [100, 4000]) assert.ok(Math.abs(distance(origin, offsetLocation(origin.latitude, origin.longitude, meters)) - meters) < .01)
  }
})

test('real delivery copy preserves approved custom text without inventing nearby or inventory claims', () => {
  const payload = { entities: [{ name: 'A real saved entity' }], title: 'Stored intention', message: 'An intention you saved may be relevant now. Revisit the evidence behind it.', reason: 'Technical critic reason', sources: ['SIMULATED'], trigger_types: ['LOCATION'] }
  const copy = notificationCopy({ payload })
  assert.equal(copy.title, 'A real saved entity')
  assert.equal(copy.context, 'Simulated · Location')
  assert.doesNotMatch(copy.body, /nearby|stocks|critic|evidence/i)
  assert.equal(notificationCopy({ payload: { ...payload, message: 'Actual approved custom delivery text.' } }).body, 'Actual approved custom delivery text.')
})

test('denied OS permission never attempts delivery or asks again', async () => {
  const priorWindow = globalThis.window, priorNotification = globalThis.Notification
  const priorNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  let calls = 0
  try {
    globalThis.window = { isSecureContext: true }
    globalThis.Notification = { permission: 'denied', requestPermission: () => { calls++; throw new Error('Unexpected permission prompt') } }
    globalThis.window.Notification = globalThis.Notification
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { serviceWorker: { get ready() { calls++; throw new Error('Unexpected delivery') } } } })
    assert.equal(notificationSupport(), 'denied')
    assert.equal(await showSystemNotification({}), false)
    assert.equal(calls, 0)
  } finally {
    if (priorWindow === undefined) delete globalThis.window; else globalThis.window = priorWindow
    if (priorNotification === undefined) delete globalThis.Notification; else globalThis.Notification = priorNotification
    if (priorNavigator) Object.defineProperty(globalThis, 'navigator', priorNavigator); else delete globalThis.navigator
  }
})
