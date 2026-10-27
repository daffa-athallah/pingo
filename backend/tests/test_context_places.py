"""Read-only preset projection; no models, geocoding, count queries or writes."""
from types import SimpleNamespace
import unittest

from backend.app.context.routes import context_places
from backend.app.domain.models import Entity


class ContextPlacesTests(unittest.TestCase):
    def test_one_read_preserves_only_coordinate_provenance_metadata(self):
        calls = []

        class Repository:
            def list_entities(self):
                calls.append('list_entities')
                return [Entity('ent_test', 'restaurant', 'food', 'Explicit test fixture', metadata={
                    'latitude': '-37.8', 'longitude': '144.967', 'location_verified': 'true',
                    'location_source': 'explicit_test_fixture', 'unrelated_private_metadata': 'must not leak',
                }), Entity('ent_unlocated', 'place', 'travel', 'Unlocated test fixture'),
                    Entity('ent_ignored', 'other', 'other', 'Unrelated fixture')]

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repository=Repository())))
        data = context_places(request)
        self.assertEqual(calls, ['list_entities'])
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['metadata']['location_source'], 'explicit_test_fixture')
        self.assertNotIn('unrelated_private_metadata', data[0]['metadata'])
        self.assertEqual(data[1]['metadata'], {})
        self.assertNotIn('eligible', data[0])
