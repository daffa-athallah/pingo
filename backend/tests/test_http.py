from contextlib import nullcontext
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.adapters.zetaris import ZetarisError
from backend.app.domain.models import Entity, Evidence, EvidenceEntity
from backend.app.main import app
from backend.app.repositories.zetaris import ZetarisRepository
from backend.tests.test_zetaris_repository import SqlHarness


class HttpSampleTests(unittest.TestCase):
    def test_sample_starts_without_sponsor_services_and_labels_result(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch('socket.socket.connect', side_effect=AssertionError('External network forbidden')):
            with TestClient(app) as client:
                health = client.get('/health').json()
                self.assertEqual((health['mode'], health['repository']), ('sample', 'InMemoryLoopRepository'))
                self.assertFalse(client.get('/sample').json()['model_calls'])
                self.assertEqual(client.get('/integration-status').json()['status'], 'integration_pending')
                events = client.get('/agent-events/run_sample').json()
                self.assertEqual([event['agent'] for event in events], ['CONTEXT', 'CRITIC'])
                self.assertTrue(all(event['receipt'] is None for event in events))

    def test_counts_come_from_evidence_edges_not_files(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), TestClient(app) as client:
            repo = app.state.repository
            entity = Entity('ent_count_test', 'place', 'food', 'Synthetic count test')
            for number in range(2):
                evidence = Evidence(f'ev_count_{number}', 'screenshot', 'food', 'Synthetic test', str(number), False, 'high', f'IMG_000{number}.PNG')
                repo.save_evidence(evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', 0.9)])
            response = client.get('/entities/ent_count_test').json()
            self.assertEqual(response['screenshot_count'], 2)
            self.assertEqual(response['inferred_intention'], None)
            self.assertEqual(client.get('/entities?domain=shopping').json(), [])
            self.assertEqual(client.get('/entities/missing').status_code, 404)

    def test_real_http_projection_uses_the_repository_without_visual_changes(self):
        sql = SqlHarness()
        self.addCleanup(sql.db.close)
        repo = ZetarisRepository(sql)
        item = Entity('ent_http', 'place', 'food', 'Synthetic real-mode API fixture')
        repo.save_entity(item)
        with patch.dict(os.environ, {'SAMPLE_MODE': 'false'}, clear=True), patch('backend.app.main.open_repository', return_value=nullcontext(repo)):
            with TestClient(app) as client:
                self.assertEqual(client.get('/entities?domain=food').json()[0]['entity_id'], item.entity_id)
                self.assertEqual(client.get('/sample').status_code, 404)

    def test_storage_errors_are_sanitized(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), TestClient(app) as client:
            with patch.object(app.state.repository, 'get_entities', side_effect=ZetarisError('private-error-payload')):
                response = client.get('/entities/any')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private-error-payload', response.text)
