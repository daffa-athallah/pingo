"""Offline location tool tests: provider responses are labelled fixtures, never model proof."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app import geocode
from backend.app.adapters.geocoding import NominatimClient
from backend.app.agents.evidence import Entity as Extracted, Evidence as Extraction, Location
from backend.app.domain.models import Entity, Evidence, EvidenceEntity
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.location_lookup import enrich_entities, enrich_evidence, signature
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.app.repositories.zetaris import ZetarisRepository
from backend.tests.test_zetaris_repository import SqlHarness

NOW = datetime(2026, 10, 27, 1, tzinfo=timezone.utc)
PLACE = Entity('ent_location_test', 'restaurant', 'food', 'Test Café', location_name='Carlton', city='Melbourne', country='Australia')


def candidate(**changes):
    return {'osm_type': 'node', 'osm_id': 123, 'name': 'Test Cafe', 'lat': '-37.8', 'lon': '144.967',
            'display_name': 'Test Cafe, Carlton, Melbourne, Australia',
            'address': {'suburb': 'Carlton', 'city': 'Melbourne', 'country': 'Australia'}, **changes}


def seed(repo, *, entity=PLACE, sensitive=False):
    evidence = Evidence('ev_location_test', 'explicit_test_fixture', entity.domain, 'Offline test fixture.', NOW.isoformat(), sensitive, 'high', 'IMG_TEST.PNG')
    repo.save_evidence(evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', .9)])
    return evidence


def resolved(entity=PLACE):
    return geocode.resolve(entity, search=lambda *args, **kwargs: [candidate()])


class MatchTests(unittest.TestCase):
    def test_unique_name_and_all_saved_locality_components_resolve(self):
        result = resolved()
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['location_id'], 'osm:node:123')
        self.assertEqual(result['lat'], -37.8)

    def test_city_is_not_discarded_as_a_generic_word(self):
        entity = replace(PLACE, location_name=None)
        result = geocode.resolve(entity, search=lambda *a, **kw: [candidate(display_name='Test Cafe, Sydney, Australia', address={'city': 'Sydney', 'country': 'Australia'})])
        self.assertEqual(result['status'], 'not_found')

    def test_wrong_country_and_wrong_suburb_do_not_resolve(self):
        for field, value in [('country', 'New Zealand'), ('location_name', 'Fitzroy')]:
            result = geocode.resolve(replace(PLACE, **{field: value}), search=lambda *a, **kw: [candidate()])
            self.assertNotEqual(result['status'], 'resolved')

    def test_business_name_containing_the_city_does_not_prove_locality(self):
        result = geocode.resolve(PLACE, search=lambda *a, **kw: [candidate(name='Test Cafe Melbourne', display_name='Test Cafe Melbourne, Sydney, Australia', address={'city': 'Sydney'})])
        self.assertNotEqual(result['status'], 'resolved')

    def test_second_query_can_reveal_another_branch_before_acceptance(self):
        calls = []
        def search(query, **kw):
            calls.append(query)
            return [candidate()] if len(calls) == 1 else [candidate(osm_id=456, lat='-37.81')]
        result = geocode.resolve(PLACE, search=search)
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(len(result['candidates']), 2)
        self.assertEqual(len(calls), 2)

    def test_duplicate_osm_results_at_same_place_are_not_duplicate_branches(self):
        self.assertEqual(geocode.resolve(PLACE, search=lambda *a, **kw: [candidate(), candidate()])['status'], 'resolved')

    def test_truncated_provider_results_stay_ambiguous(self):
        rows = [candidate(osm_id=i) for i in range(5)]
        self.assertEqual(geocode.resolve(PLACE, search=lambda *a, **kw: rows)['status'], 'ambiguous')

    def test_missing_locality_does_not_send_a_search(self):
        result = geocode.resolve(replace(PLACE, city=None, location_name=None), search=lambda *a: self.fail('No request expected'))
        self.assertEqual(result['status'], 'ambiguous')

    def test_name_only_fallback_keeps_the_original_locality_requirements(self):
        def search(query, **kwargs):
            return [candidate()] if query == PLACE.name else []
        self.assertEqual(geocode.resolve(PLACE, search=search)['status'], 'resolved')
        wrong_city = replace(PLACE, city='Sydney')
        self.assertNotEqual(geocode.resolve(wrong_city, search=search)['status'], 'resolved')

    def test_invalid_coordinates_or_provenance_never_become_verified(self):
        for row in [candidate(lat='NaN'), candidate(lon='181'), candidate(osm_id=None), candidate(name=123)]:
            self.assertNotEqual(geocode.resolve(PLACE, search=lambda *a, **kw: [row])['status'], 'resolved')

    def test_validated_area_boundary_can_support_a_missing_address_component(self):
        area = {'name': 'Carlton', 'class': 'boundary', 'osm_type': 'relation', 'osm_id': 77,
                'display_name': 'Carlton, Melbourne, Australia', 'address': {'city': 'Melbourne', 'country': 'Australia'},
                'boundingbox': ['-37.82', '-37.78', '144.95', '144.99']}
        def search(query, **kwargs):
            if kwargs.get('viewbox'):
                return [candidate(display_name='Test Cafe, Melbourne, Australia', address={'city': 'Melbourne', 'country': 'Australia'})]
            return [area] if query.startswith('Carlton,') else []
        self.assertEqual(geocode.resolve(PLACE, search=search)['status'], 'resolved')

    def test_area_fallback_never_uses_an_unrelated_first_region(self):
        bad_area = {'name': 'Carlton', 'class': 'boundary', 'osm_type': 'relation', 'osm_id': 77,
                    'display_name': 'Carlton, Sydney, Australia', 'boundingbox': ['-34', '-33', '150', '151']}
        def search(query, **kwargs):
            self.assertNotIn('viewbox', kwargs)
            return [bad_area] if query.startswith('Carlton,') else []
        self.assertEqual(geocode.resolve(PLACE, search=search)['status'], 'not_found')

    def test_product_is_not_geocoded_as_a_shop(self):
        product = replace(PLACE, domain='shopping', entity_type='product', brand='Test brand')
        self.assertEqual(geocode.resolve(product, search=lambda *a: self.fail('No product search'))['status'], 'skipped')
        store = replace(PLACE, domain='shopping', entity_type='store')
        self.assertEqual(geocode.metadata_for(store, resolved(store))['location_role'], 'store')
        self.assertNotIn('inventory', geocode.metadata_for(store, resolved(store)))

    def test_geocoder_outage_is_explicit_and_safe(self):
        def failing(*args):
            raise OSError('Fixture failure')
        self.assertEqual(geocode.resolve(PLACE, search=failing)['status'], 'unavailable')

    def test_sample_and_unconfigured_modes_do_not_enable_network(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertFalse(geocode.enabled())
        with patch.dict('os.environ', {'SAMPLE_MODE': 'true', 'RECALL_GEOCODE': 'on'}):
            self.assertFalse(geocode.enabled())


class TransportTests(unittest.TestCase):
    def test_success_and_negative_results_are_cached_across_client_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def transport(query, **kw):
                calls.append(query)
                return [candidate()] if query == 'located' else []
            first = NominatimClient(cache_dir=tmp, transport=transport, sleep=lambda _: None)
            self.assertEqual(first.search('located')[0]['osm_id'], 123)
            second = NominatimClient(cache_dir=tmp, transport=transport, sleep=lambda _: None)
            second.search('located'); second.search('missing'); second.search('missing')
            self.assertEqual(calls, ['located', 'missing'])

    def test_serial_requests_are_throttled_even_on_a_new_client_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            sleeps = []
            client = NominatimClient(cache_dir=tmp, transport=lambda *a, **kw: [], clock=lambda: 100, sleep=sleeps.append)
            client.search('first')
            NominatimClient(cache_dir=tmp, transport=lambda *a, **kw: [], clock=lambda: 100, sleep=sleeps.append).search('second')
            self.assertEqual(len(sleeps), 1)
            self.assertAlmostEqual(sleeps[0], 1.1)

    def test_failure_backoff_prevents_repeated_network_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def fail(*a, **kw):
                calls.append(1)
                raise OSError('Fixture failure')
            client = NominatimClient(cache_dir=tmp, transport=fail, clock=lambda: 100, sleep=lambda _: None)
            for query in ['one', 'two']:
                with self.assertRaises(OSError): client.search(query)
            self.assertEqual(len(calls), 1)

    def test_credentials_in_provider_url_are_rejected(self):
        with self.assertRaises(ValueError): NominatimClient(endpoint='https://user:secret@example.org/search')


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flag = patch.dict('os.environ', {'RECALL_GEOCODE': 'on', 'SAMPLE_MODE': 'false'})
        self.flag.start(); self.addCleanup(self.flag.stop)
        self.repo = InMemoryLoopRepository()
        self.evidence = seed(self.repo)

    async def test_resolved_entity_metadata_persists_without_mutating_evidence_or_identity(self):
        original = dict(self.repo.evidence)
        rows = await enrich_evidence(self.repo, self.evidence.evidence_id, resolver=resolved, clock=lambda: NOW)
        self.assertEqual(rows[0]['status'], 'resolved')
        self.assertTrue(rows[0]['persisted'])
        self.assertEqual(self.repo.evidence, original)
        self.assertEqual(self.repo.entities[PLACE.entity_id].entity_id, PLACE.entity_id)
        self.assertTrue(geocode.verified(self.repo.entities[PLACE.entity_id]))

    async def test_sql_repository_roundtrip_uses_existing_save_entity_helper(self):
        sql = SqlHarness(); self.addCleanup(sql.db.close)
        repo = ZetarisRepository(sql); seed(repo)
        await enrich_entities(repo, [PLACE], resolver=resolved, clock=lambda: NOW)
        self.assertTrue(geocode.verified(repo.get_entities([PLACE.entity_id])[0]))
        self.assertEqual(repo.get_evidence(self.evidence.evidence_id), self.evidence)

    async def test_dry_run_performs_no_entity_mutation(self):
        rows = await enrich_entities(self.repo, [PLACE], resolver=resolved, clock=lambda: NOW, persist=False)
        self.assertEqual(self.repo.entities[PLACE.entity_id], PLACE)
        self.assertFalse(rows[0]['persisted'])

    async def test_missing_or_sensitive_evidence_never_reaches_provider(self):
        repo = InMemoryLoopRepository(); evidence = seed(repo, sensitive=True)
        self.assertEqual(await enrich_evidence(repo, evidence.evidence_id, resolver=lambda e: self.fail('Private query')), [])
        rows = await enrich_entities(repo, [PLACE], resolver=lambda e: self.fail('Private query'))
        self.assertNotIn('name', rows[0])

    async def test_ambiguity_persists_auditable_candidates_and_does_not_retry_on_every_upload(self):
        calls = []
        def ambiguous(entity):
            calls.append(1)
            return {'status': 'ambiguous', 'reason': 'Explicit multiple-branch fixture.', 'candidates': [{'label': 'Candidate fixture'}]}
        await enrich_entities(self.repo, [PLACE], resolver=ambiguous, clock=lambda: NOW)
        current = self.repo.get_entities([PLACE.entity_id])[0]
        self.assertEqual(current.metadata['location_verified'], 'false')
        await enrich_entities(self.repo, [current], resolver=ambiguous, clock=lambda: NOW+timedelta(minutes=1))
        self.assertEqual(len(calls), 1)

    async def test_new_user_pin_during_lookup_is_not_overwritten(self):
        def user_pin(entity):
            self.repo.save_entity(replace(entity, metadata=geocode.metadata_from_pin(entity, -37.81, 144.98, how='Explicit user fixture')))
            return resolved(entity)
        rows = await enrich_entities(self.repo, [PLACE], resolver=user_pin, clock=lambda: NOW)
        self.assertEqual(rows[0]['status'], 'located')
        self.assertEqual(float(self.repo.entities[PLACE.entity_id].metadata['latitude']), -37.81)

    async def test_entity_change_during_lookup_rejects_stale_result(self):
        def changed(entity):
            self.repo.save_entity(replace(entity, city='Sydney'))
            return resolved(entity)
        rows = await enrich_entities(self.repo, [PLACE], resolver=changed, clock=lambda: NOW)
        self.assertEqual(rows[0]['status'], 'stale')
        self.assertNotIn('latitude', self.repo.entities[PLACE.entity_id].metadata)

    async def test_save_failure_does_not_claim_location_was_persisted(self):
        with patch.object(self.repo, 'save_entity', side_effect=RuntimeError('Fixture write failure')):
            rows = await enrich_entities(self.repo, [PLACE], resolver=resolved, clock=lambda: NOW)
        self.assertEqual(rows[0]['status'], 'store_failed')
        self.assertIsNone(rows[0]['latitude'])

    async def test_failure_metadata_is_replaced_by_a_later_success(self):
        await enrich_entities(self.repo, [PLACE], resolver=lambda e: {'status': 'unavailable', 'reason': 'Fixture outage'}, clock=lambda: NOW)
        current = self.repo.entities[PLACE.entity_id]
        await enrich_entities(self.repo, [current], resolver=resolved, clock=lambda: NOW+timedelta(minutes=10))
        self.assertEqual(self.repo.entities[PLACE.entity_id].metadata['location_lookup_status'], 'resolved')

    async def test_invalidated_success_is_not_hidden_behind_a_retry_timestamp(self):
        broken = replace(PLACE, metadata={'location_verified': 'false', 'location_lookup_status': 'resolved',
                         'location_lookup_signature': signature(PLACE), 'location_lookup_retry_at': (NOW+timedelta(days=1)).isoformat()})
        self.repo.save_entity(broken)
        rows = await enrich_entities(self.repo, [broken], resolver=resolved, clock=lambda: NOW)
        self.assertEqual(rows[0]['status'], 'resolved')
        self.assertTrue(geocode.verified(self.repo.entities[PLACE.entity_id]))


class IngestionPreservationTests(unittest.TestCase):
    def test_another_screenshot_preserves_verified_metadata_and_rejects_perception_spoofing(self):
        repo = InMemoryLoopRepository()
        extracted = Extracted('Test Cafe', 'restaurant', location=Location('Carlton', 'Melbourne', 'Australia'))
        extraction = Extraction('food', 'Explicit fixture', [extracted], False, 'high')
        first = ingest(extraction, repo)
        entity = first.entities[0]
        metadata = geocode.metadata_for(entity, resolved(entity))
        repo.save_entity(replace(entity, metadata=metadata))
        spoof = replace(extracted, attributes={'price': '10', 'latitude': '0', 'longitude': '0', 'location_verified': 'true'})
        second = ingest(replace(extraction, entities=[spoof]), repo)
        self.assertEqual(second.entities[0].metadata['latitude'], metadata['latitude'])
        self.assertEqual(second.entities[0].metadata['price'], '10')
        self.assertEqual(len(repo.evidence), 2)
        self.assertEqual(repo.evidence[first.evidence.evidence_id], first.evidence)

    def test_new_place_cannot_forge_verified_coordinates_from_vision_attributes(self):
        entity = Extracted('Test Cafe', 'restaurant', attributes={'latitude': '0', 'location_verified': 'true'})
        record = ingest(Extraction('food', 'Explicit fixture', [entity], False, 'high'), InMemoryLoopRepository())
        self.assertEqual(record.entities[0].metadata, {})

    def test_conflicting_new_suburb_invalidates_an_old_pin_without_changing_identity(self):
        repo = InMemoryLoopRepository()
        extracted = Extracted('Test Cafe', 'restaurant', location=Location('Carlton', 'Melbourne', 'Australia'))
        extraction = Extraction('food', 'Explicit fixture', [extracted], False, 'high')
        first = ingest(extraction, repo)
        entity = first.entities[0]
        repo.save_entity(replace(entity, metadata=geocode.metadata_for(entity, resolved(entity))))
        second = ingest(replace(extraction, entities=[replace(extracted, location=Location('Fitzroy', 'Melbourne', 'Australia'))]), repo)
        self.assertEqual(first.entities[0].entity_id, second.entities[0].entity_id)
        self.assertEqual(second.entities[0].metadata['location_verified'], 'false')
        self.assertEqual(second.entities[0].metadata['location_lookup_status'], 'context_changed')
