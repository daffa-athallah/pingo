import test from 'node:test'
import assert from 'node:assert/strict'
import { sortCollection, verifiedCatalogueImage } from '../src/data/collectionPresentation.ts'

test('recent order uses screenshot time, puts missing dates last, and never mutates input', () => {
  const input = [{ id: 'a', latestScreenshotAt: '2026-10-01T00:00:00Z', screenshotCount: 5 },
    { id: 'b', latestScreenshotAt: '2026-10-25T00:00:00Z', screenshotCount: 1 }, { id: 'c', screenshotCount: 3 }]
  assert.deepEqual(sortCollection(input, 'recent').map(i => i.id), ['b', 'a', 'c'])
  assert.deepEqual(input.map(i => i.id), ['a', 'b', 'c'])
  assert.deepEqual(sortCollection(input, 'screenshots').map(i => i.id), ['a', 'c', 'b'])
})

test('catalogue images require verified provenance and the exact single entity', () => {
  const image = { entity_id: 'entity_a', catalogue_image_url: 'https://example.org/item.jpg',
    catalogue_image_source: 'https://example.org/product', catalogue_image_verified: true, alt: 'Exact saved item' }
  const loop = { entities: [{ entity_id: 'entity_a' }], catalogue_images: [image] }
  assert.equal(verifiedCatalogueImage(loop).url, image.catalogue_image_url)
  for (const changes of [{ entity_id: 'other' }, { catalogue_image_verified: false }, { catalogue_image_source: '' },
    { catalogue_image_url: 'file:///Users/private/image.png' }, { catalogue_image_url: '/Users/private/image.png' },
    { catalogue_image_url: 'javascript:alert(1)' }, { catalogue_image_url: 'https://secret:token@example.org/image.jpg' },
    { catalogue_image_source: '/Users/private/source' }, { alt: '' }]) {
    assert.equal(verifiedCatalogueImage({ ...loop, catalogue_images: [{ ...image, ...changes }] }), undefined)
  }
  assert.equal(verifiedCatalogueImage({ ...loop, entities: [{ entity_id: 'entity_a' }, { entity_id: 'entity_b' }] }), undefined)
  assert.equal(verifiedCatalogueImage({ entities: [] }), undefined)
})
