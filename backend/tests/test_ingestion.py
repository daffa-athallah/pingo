"""Offline ingestion bridge checks: extraction -> canonical records -> repository -> Open Loop Agent."""
import json
import unittest

from backend.app.agents.evidence import Entity, Evidence, EvidenceError, Location, parse_evidence
from backend.app.agents.open_loop import Decision, OpenLoopAgent
from backend.app.ingestion.evidence_bridge import entity_id, ingest
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.tests.test_open_loop import FakeGateway

BURGER = Entity('OMB Burger', 'restaurant', 'restaurant', None, None, Location('Melbourne CBD', 'Melbourne', 'Australia'),
                {'price': 'under $10', 'halal': 'yes'})


def extraction(**kw):
    base = dict(domain='food', summary='A burger shop video.', entities=[BURGER], sensitive=False, confidence='high')
    return Evidence(**{**base, **kw})


class BridgeTests(unittest.TestCase):
    def ingest(self, repo=None, **kw):
        repo = repo or InMemoryLoopRepository()
        return repo, ingest(extraction(**kw), repo, image_ref='screenshot/a.png', captured_at='2026-10-25T10:00:00+00:00',
                            new_id=lambda: 'ev_fixed')

    def test_maps_to_canonical_records_and_persists(self):
        repo, result = self.ingest()
        self.assertEqual((result.evidence.evidence_id, result.evidence.source, result.evidence.image_ref,
                          result.evidence.timestamp),
                         ('ev_fixed', 'screenshot', 'screenshot/a.png', '2026-10-25T10:00:00+00:00'))
        entity = result.entities[0]
        self.assertEqual((entity.name, entity.entity_type, entity.domain, entity.category),
                         ('OMB Burger', 'restaurant', 'food', 'restaurant'))
        self.assertEqual((entity.location_name, entity.city, entity.country), ('Melbourne CBD', 'Melbourne', 'Australia'))
        self.assertEqual(entity.metadata, {'price': 'under $10', 'halal': 'yes'})
        self.assertNotIn('location', entity.metadata)
        link = result.links[0]
        self.assertEqual((link.evidence_id, link.entity_id, link.relationship), ('ev_fixed', entity.entity_id, 'depicted'))
        self.assertEqual(repo.evidence['ev_fixed'], result.evidence)
        self.assertEqual(repo.entities[entity.entity_id], entity)
        self.assertEqual(repo.evidence_entities, [link])

    def test_ids_are_generated_unique_and_entity_ids_stable(self):
        repo = InMemoryLoopRepository()
        a = ingest(extraction(), repo)
        b = ingest(extraction(), repo)
        self.assertNotEqual(a.evidence.evidence_id, b.evidence.evidence_id)
        self.assertTrue(a.evidence.evidence_id.startswith('ev_'))
        self.assertEqual(a.entities[0].entity_id, b.entities[0].entity_id)
        self.assertEqual(len(repo.entities), 1)
        self.assertEqual(len(repo.evidence), 2)
        other = Entity('OMB Burger', 'restaurant', location=Location('Sydney', 'Sydney', None))
        self.assertNotEqual(entity_id('food', BURGER), entity_id('food', other))

    def test_duplicate_entities_in_one_screenshot_collapse(self):
        _, result = self.ingest(entities=[BURGER, BURGER])
        self.assertEqual((len(result.entities), len(result.links)), (1, 1))

    def test_sensitive_evidence_keeps_flag_but_drops_attributes(self):
        repo, result = self.ingest(sensitive=True)
        self.assertTrue(repo.evidence['ev_fixed'].sensitive)
        self.assertEqual(result.entities[0].metadata, {})

    def test_invalid_extraction_is_never_persisted(self):
        repo = InMemoryLoopRepository()
        with self.assertRaises(EvidenceError):
            ingest(parse_evidence(json.dumps({'domain': 'food'})), repo)
        self.assertEqual((repo.evidence, repo.entities, repo.evidence_entities), ({}, {}, []))


class IdentityAndLocationTests(unittest.TestCase):
    def test_classification_and_location_name_do_not_change_entity_id(self):
        ids = set()
        for type_, category, sub, loc_name in (('place', None, None, 'OMB Burger'), ('venue', 'food', 'burgers', 'Melbourne CBD'),
                                               ('restaurant', 'restaurant', 'halal', None), ('RESTAURANT', None, None, 'Carlton')):
            ids.add(entity_id('food', Entity('  OMB   Burger ', type_, category, sub, None, Location(loc_name, ' melbourne', 'Australia'))))
        self.assertEqual(len(ids), 1)
        self.assertEqual(entity_id('Food', Entity('omb burger', 'x', location=Location(None, 'MELBOURNE', None))), ids.pop())

    def test_identity_inputs_by_domain(self):
        self.assertNotEqual(entity_id('food', Entity('OMB Burger', 'x', location=Location(None, 'Melbourne', None))),
                            entity_id('food', Entity('OMB Burger', 'x', location=Location(None, 'Sydney', None))))
        self.assertNotEqual(entity_id('travel', Entity('Shibuya Sky', 'x')), entity_id('food', Entity('Shibuya Sky', 'x')))
        zara = Entity('Brown jacket', 'product', brand='Zara', location=Location(None, 'Melbourne', None))
        self.assertEqual(entity_id('shopping', zara),
                         entity_id('shopping', Entity(' brown JACKET', 'clothing', 'apparel', brand=' ZARA')))
        self.assertNotEqual(entity_id('shopping', zara), entity_id('shopping', Entity('Brown jacket', 'product', brand='H&M')))

    def test_location_name_repeating_entity_name_becomes_null(self):
        raw = {**{'domain': 'food', 'summary': 's', 'sensitive': False, 'confidence': 'high'}, 'entities': [
            {'name': 'OMB Burger', 'type': 'place', 'location': {'location_name': 'omb  burger', 'city': 'Melbourne', 'country': 'Australia'}},
            {'name': 'Cafe', 'type': 'place', 'location': {'location_name': 'cafe', 'city': None, 'country': None}},
            {'name': 'Pizza', 'type': 'place', 'attributes': {'location': 'Pizza'}},
            {'name': 'Gelato', 'type': 'place', 'location': {'location_name': 'Carlton', 'city': 'Melbourne', 'country': None}}]}
        entities = parse_evidence(json.dumps(raw)).entities
        self.assertEqual(entities[0].location, Location(None, 'Melbourne', 'Australia'))
        self.assertIsNone(entities[1].location)
        self.assertIsNone(entities[2].location)
        self.assertEqual(entities[3].location.location_name, 'Carlton')
        # A hand-built entity is cleaned again at the bridge, so storage never holds a duplicated name.
        repo = InMemoryLoopRepository()
        stored = ingest(extraction(entities=[Entity('Cafe', 'place', location=Location('Cafe', 'Melbourne', None))]), repo).entities[0]
        self.assertEqual((stored.location_name, stored.city), (None, 'Melbourne'))

    def test_domain_evidence_has_no_possible_intent(self):
        result = ingest(extraction(), InMemoryLoopRepository())
        self.assertNotIn('possible_intent', vars(result.evidence))


class BridgeToOpenLoopTests(unittest.IsolatedAsyncioTestCase):
    def reply(self, evidence_id, entity_id_, **kw):
        base = {'decision': 'CREATE', 'target_loop_id': None, 'proposed_title': 'Interested in OMB Burger',
                'domain': 'food', 'confidence': 0.6, 'concise_reason': 'Saved a venue.',
                'supporting_evidence_ids': [evidence_id], 'supporting_entity_ids': [entity_id_], 'material_uncertainty': None}
        return json.dumps({**base, **kw})

    async def test_bridge_output_is_consumed_by_open_loop_agent(self):
        repo = InMemoryLoopRepository()
        result = ingest(extraction(), repo, new_id=lambda: 'ev_1')
        eid = result.entities[0].entity_id
        gateway = FakeGateway(self.reply('ev_1', eid))
        decision, loop = await OpenLoopAgent(gateway, repo, new_id=lambda: 'loop_1').process(result.evidence, result.entities)
        self.assertEqual((decision.decision, loop.loop_id), (Decision.CREATE, 'loop_1'))
        sent = json.loads(gateway.calls[0]['messages'][1]['content'])
        self.assertEqual(sent['new_entities'][0]['location_name'], 'Melbourne CBD')
        self.assertNotIn('possible_intent', sent['new_evidence'])
        self.assertFalse(hasattr(result.evidence, 'possible_intent'))
        self.assertEqual([(l.loop_id, l.entity_id) for l in repo.loop_entities], [('loop_1', eid)])

    async def test_second_screenshot_sees_first_as_related_evidence(self):
        repo = InMemoryLoopRepository()
        first = ingest(extraction(), repo, new_id=lambda: 'ev_1')
        second = ingest(extraction(summary='Same venue again.'), repo, new_id=lambda: 'ev_2')
        gateway = FakeGateway(self.reply('ev_2', second.entities[0].entity_id, supporting_evidence_ids=['ev_2', 'ev_1']))
        await OpenLoopAgent(gateway, repo).decide(second.evidence, second.entities)
        sent = json.loads(gateway.calls[0]['messages'][1]['content'])
        self.assertEqual([e['evidence_id'] for e in sent['related_evidence']], ['ev_1'])

    async def test_sensitive_evidence_never_reaches_the_model(self):
        repo = InMemoryLoopRepository()
        result = ingest(extraction(sensitive=True), repo)
        gateway = FakeGateway()
        decision, loop = await OpenLoopAgent(gateway, repo).process(result.evidence, result.entities)
        self.assertEqual((decision.decision, loop, gateway.calls), (Decision.IGNORE, None, []))


if __name__ == '__main__':
    unittest.main()
