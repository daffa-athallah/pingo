"""The resettable demo workspace: seeded from the committed snapshot, real-model path (scripted here), isolated from canonical data."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.bootstrap import app_mode
from backend.app.demo_workspace import open_demo_repository, read_snapshot, workspace_info
from backend.app.main import app
from backend.tests.test_upload_api import FakeGateway, PNG


class Snapshot(unittest.TestCase):
    def test_snapshot_is_the_historical_state(self):
        data = read_snapshot()
        counts = data['meta']['counts']
        self.assertEqual((counts['evidence'], counts['entities'], counts['evidence_entities'], counts['active_loops']), (30, 65, 69, 17))
        repository = open_demo_repository()
        self.assertEqual((len(repository.list_evidence()), len(repository.list_entities()), len(repository.get_active_open_loops(limit=100))), (30, 65, 17))
        self.assertEqual(sum(e.sensitive for e in repository.list_evidence()), 0)
        self.assertEqual(workspace_info(data)['storage'], 'in-memory, resettable')

    def test_modes_are_explicit_and_exclusive(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(app_mode(), 'real')
        with patch.dict(os.environ, {'RECALL_MODE': 'demo'}, clear=True):
            self.assertEqual(app_mode(), 'demo')
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True):
            self.assertEqual(app_mode(), 'sample')
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true', 'RECALL_MODE': 'demo'}, clear=True), self.assertRaises(ValueError):
            app_mode()
        with patch.dict(os.environ, {'RECALL_MODE': 'whatever'}, clear=True), self.assertRaises(ValueError):
            app_mode()


class DemoApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.gateway = FakeGateway()

        @asynccontextmanager
        async def gateway():
            yield self.gateway

        for item in (patch.dict(os.environ, {'RECALL_MODE': 'demo'}, clear=True), patch('backend.app.main.RUNTIME', self.runtime),
                     patch('backend.app.runs_api.RUNTIME', self.runtime), patch('backend.app.upload_api._gateway', gateway)):
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_starts_from_the_snapshot_and_says_what_it_is(self):
        health = self.client.get('/health').json()
        self.assertEqual((health['mode'], health['workspace'], health['repository']), ('demo', 'demo', 'InMemoryLoopRepository'))
        self.assertEqual(health['demo_workspace']['storage'], 'in-memory, resettable')
        self.assertEqual(len(self.client.get('/open-loops').json()), 17)
        status = self.client.get('/integration-status').json()
        self.assertEqual((status['zetaris'], status['workspace'], status['saved_reasoning_runs']), (None, 'demo', []))  # not Zetaris, and no one else's runs

    def test_upload_then_reset_restores_the_snapshot_and_touches_nothing_canonical(self):
        before = {l['loop_id']: l['screenshot_count'] for l in self.client.get('/open-loops').json()}
        body = self.client.post('/api/screenshots?wait=1', content=PNG, headers={'Content-Type': 'image/png'}).json()
        self.assertEqual((body['workspace'], body['provenance']), ('demo', 'live'))
        events = {f"{e['agent']}:{e['action']}": e for e in body['result']['trace_events']}
        self.assertIn('REPOSITORY:STORE', events)  # honest label: this is not Zetaris
        self.assertNotIn('ZETARIS:STORE', events)
        self.assertEqual(events['REPOSITORY:STORE']['detail']['backend'], 'in-memory demo workspace')
        self.assertEqual(len(app.state.repository.list_evidence()), 31)
        self.assertEqual(len(self.client.get('/open-loops').json()), 18)  # the new loop is visible at once
        self.assertEqual(len(self.client.get('/runs').json()), 1)
        self.assertTrue(list((self.runtime / 'demo' / 'uploads').glob('upload-*')))
        self.assertFalse((self.runtime / 'uploads').exists() or (self.runtime / 'live_runs').exists())  # canonical folders untouched

        reset = self.client.post('/api/demo/reset').json()
        self.assertEqual((reset['evidence'], reset['active_loops']), (30, 17))
        self.assertEqual({l['loop_id']: l['screenshot_count'] for l in self.client.get('/open-loops').json()}, before)
        self.assertEqual((self.client.get('/runs').json(), list((self.runtime / 'demo' / 'uploads').glob('upload-*'))), ([], []))
        again = self.client.post('/api/screenshots?wait=1', content=PNG, headers={'Content-Type': 'image/png'}).json()  # not a duplicate after reset
        self.assertNotEqual(again['outcome']['status'], 'duplicate')


class ResetIsDemoOnly(unittest.TestCase):
    def test_no_reset_outside_the_demo_workspace(self):
        for env in ({'SAMPLE_MODE': 'true'},):
            with patch.dict(os.environ, env, clear=True), TestClient(app) as client:
                self.assertEqual(client.post('/api/demo/reset').status_code, 404)


if __name__ == '__main__':
    unittest.main()
