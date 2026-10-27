"""The existing screenshot pipeline automatically calls the location tool after saving.

Both model and map replies below are explicit offline fixtures.
"""
from unittest.mock import patch

from backend.tests.test_upload_api import Base, PNG2


def map_fixture(entity):
    return {'status': 'resolved', 'lat': -37.8, 'lon': 144.967,
            'location_id': 'osm:node:123', 'display_name': 'Explicit test restaurant, Carlton, Melbourne, Australia', 'candidates': []}


class UploadLocationTests(Base):
    def test_automatic_lookup_is_observed_and_does_not_add_model_calls(self):
        with patch.dict('os.environ', {'RECALL_GEOCODE': 'on'}), patch('backend.app.geocode.resolve', side_effect=map_fixture) as resolver:
            response = self.post()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['outcome']['locations'][0]['status'], 'resolved')
        self.assertTrue(result['outcome']['locations'][0]['persisted'])
        self.assertEqual(self.gateway.calls, ['vision', 'reasoning'])
        self.assertEqual(resolver.call_count, 1)
        traces = self.events(result['run_id'])
        location = next(event for event in traces if event['agent'] == 'LOCATION')
        self.assertIsNone(location['receipt'])  # a map response is not a fabricated model receipt
        evidence = self.repo.get_evidence(result['outcome']['evidence']['evidence_id'])
        self.assertEqual(evidence.summary, 'A burger place menu in Carlton.')

    def test_lookup_failure_keeps_the_original_image_evidence_and_agent_result(self):
        with patch.dict('os.environ', {'RECALL_GEOCODE': 'on'}), patch('backend.app.geocode.resolve', side_effect=OSError('Explicit fixture outage')):
            response = self.post()
        result = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result['outcome']['status'], 'stored')
        self.assertEqual(result['outcome']['locations'][0]['status'], 'unavailable')
        self.assertEqual(len(self.uploads), 1)
        self.assertIsNotNone(self.repo.get_evidence(result['outcome']['evidence']['evidence_id']))

    def test_sensitive_screenshot_never_triggers_an_external_location_query(self):
        self.gateway.sensitive = True
        with patch.dict('os.environ', {'RECALL_GEOCODE': 'on'}), patch('backend.app.geocode.resolve') as resolver:
            result = self.post().json()
        resolver.assert_not_called()
        self.assertEqual(result['outcome']['locations'], [])

    def test_another_screenshot_of_the_same_entity_preserves_the_resolved_location(self):
        with patch.dict('os.environ', {'RECALL_GEOCODE': 'on'}), patch('backend.app.geocode.resolve', side_effect=map_fixture) as resolver:
            first = self.post().json()
            second = self.post(PNG2).json()
        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(second['outcome']['locations'][0]['status'], 'located')
        self.assertNotEqual(first['outcome']['evidence']['evidence_id'], second['outcome']['evidence']['evidence_id'])
