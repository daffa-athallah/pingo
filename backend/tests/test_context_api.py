"""Offline tests for POST /api/context/evaluate, the read-only overlay, the privacy gate and CORS settings. Sample mode: no model, no network."""
from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.context_policy import sensitive_reason
from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.main import app
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.app.repositories.overlay import ReadOnlyOverlayRepository

NOW = '2026-10-26T10:00:00+00:00'
EVENT = {'context_type': 'CALENDAR', 'title': 'Dinner with Alex', 'occurs_at': '2026-10-27T19:00:00+11:00', 'location_name': 'Carlton', 'city': 'Melbourne'}


def snapshot(repo):
    return ({k: v for k, v in repo.loops.items()}, list(repo.loop_entities), dict(repo.evidence), dict(repo.check_ins))


class Overlay(unittest.TestCase):
    def test_loop_writes_stay_in_memory_and_other_writes_are_refused(self):
        base = InMemoryLoopRepository()
        base.save_open_loop(OpenLoop('l1', 'Old title', 'food', LoopStatus.OPEN, 0.7, NOW, NOW))
        before = snapshot(base)
        view = ReadOnlyOverlayRepository(base)
        view.update_open_loop('l1', title='New title', updated_at='later')
        view.link_loop_entity(LoopEntity('l1', 'e1', 'subject', 0.5))
        self.assertEqual(view.get_open_loop('l1').title, 'New title')
        self.assertEqual(view.get_active_open_loops()[0].title, 'New title')
        self.assertEqual(len(view.get_loop_entities(['l1'])), 1)
        self.assertEqual(snapshot(base), before)
        with self.assertRaises(PermissionError):
            view.save_evidence(Evidence('ev', 's', 'food', 'x', NOW, False, 'high'), [], [])
        with self.assertRaises(PermissionError):
            view.save_check_in(None)


class PrivacyGate(unittest.TestCase):
    def test_private_titles_are_caught_and_ordinary_ones_pass(self):
        for text in ('Appointment with Dr Lee', 'Konsultasi dokter', 'Bank meeting', 'Therapy session', 'Lawyer at 3pm'):
            self.assertIsNotNone(sensitive_reason(text), text)
        for text in ('Dinner with Alex', 'Pick up dry cleaning', 'Carlton', None):
            self.assertIsNone(sensitive_reason(text), text)


class EvaluateApi(unittest.TestCase):
    def client(self):
        env = patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def test_surface_payload_has_why_now_evidence_context_and_does_not_write(self):
        client = self.client()
        before = snapshot(app.state.repository)
        body = client.post('/api/context/evaluate', json={'events': [EVENT], 'synthetic': True}).json()
        self.assertEqual(body['final_action'], 'SURFACE')
        self.assertTrue(body['synthetic'])
        surface = body['surface']
        self.assertTrue(surface['why_now'] and surface['evidence'] and surface['loop']['title'])
        self.assertEqual([c['title'] for c in surface['context']], ['Dinner with Alex'])
        self.assertEqual([e['agent'] for e in body['result']['trace_events']], ['CONTEXT', 'CRITIC'])
        self.assertEqual(snapshot(app.state.repository), before)
        self.assertEqual(client.get(f"/api/runs/{body['run_id']}").json()['result']['run_id'], body['run_id'])
        self.assertEqual(len(client.get(f"/agent-events/{body['run_id']}").json()), 2)

    def test_validation_and_privacy(self):
        client = self.client()
        self.assertEqual(client.post('/api/context/evaluate', json={'events': []}).status_code, 422)
        self.assertEqual(client.post('/api/context/evaluate', json={'events': [dict(EVENT, context_type='REAL_WORLD_EVENT')]}).status_code, 422)
        self.assertEqual(client.post('/api/context/evaluate', json={'events': [EVENT] * 6}).status_code, 422)
        private = client.post('/api/context/evaluate', json={'events': [dict(EVENT, title='Appointment with my psychologist')]}).json()
        self.assertEqual((private['final_action'], private['run_id'], private['surface']), ('STAY_SILENT', None, None))
        self.assertNotIn('psychologist', str(private))

    def test_unknown_run_is_404(self):
        self.assertEqual(self.client().get('/api/runs/nope').status_code, 404)


class Cors(unittest.TestCase):
    def test_extra_origins_come_from_the_environment(self):
        import importlib
        import backend.app.main as main
        with patch.dict(os.environ, {'RECALL_CORS_ORIGINS': 'https://a.ts.net/, https://b.ts.net:5173'}):
            importlib.reload(main)
            self.assertIn('https://a.ts.net', main._ORIGINS)
            self.assertIn('https://b.ts.net:5173', main._ORIGINS)
        importlib.reload(main)
        self.assertNotIn('https://a.ts.net', main._ORIGINS)


if __name__ == '__main__':
    unittest.main()
