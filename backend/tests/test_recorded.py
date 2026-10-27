"""Replays must reject changed inputs, consume real captures and stay offline."""
import asyncio
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.main import app
from backend.app.recorded import RecordedGateway, request_signature, load_recording
from backend.app.sample_cases import CASES, replay_case


class ReplayBoundary(unittest.TestCase):
    def test_nonces_do_not_affect_identity_but_context_prompts_and_models_do(self):
        messages = [{'role': 'system', 'content': 'Example prompt'}, {'role': 'user', 'content': json.dumps({'request_id': 'a', 'title': 'Dinner'})}]
        expected = request_signature(messages, {'model': 'example'})
        messages[-1]['content'] = json.dumps({'request_id': 'b', 'title': 'Dinner'})
        self.assertEqual(request_signature(messages, {'model': 'example'}), expected)
        self.assertNotEqual(request_signature(messages, {'model': 'other'}), expected)
        messages[-1]['content'] = json.dumps({'request_id': 'a', 'title': 'Laundry'})
        self.assertNotEqual(request_signature(messages, {'model': 'example'}), expected)
        self.assertNotIn('Dinner', expected)

    def test_wrong_request_and_exhaustion_fail_without_returning_a_reply(self):
        bundle = load_recording('surface')
        gateway = RecordedGateway(bundle)
        with self.assertRaisesRegex(ModelGatewayError, 'differs'):
            asyncio.run(gateway.complete([{'role': 'user', 'content': 'unrelated'}]))
        self.assertEqual(gateway.position, 0)
        self.assertEqual(gateway.last_routing, {})
        gateway.position = len(gateway.calls)
        with self.assertRaisesRegex(ModelGatewayError, 'exhausted'):
            asyncio.run(gateway.complete([]))

    def test_all_bundled_cases_execute_offline_and_exercise_the_claimed_outcomes(self):
        with patch.dict(os.environ, {}, clear=True), patch('socket.socket.connect', side_effect=AssertionError('No network')):
            records = {case: asyncio.run(replay_case(case)) for case in CASES}
        for record in records.values():
            self.assertEqual((record['provenance'], record['workspace'], record['status']), ('recorded', 'sample', 'done'))
            self.assertIsNone(record['result']['error'])
            self.assertFalse(any(e['agent'] == 'ZETARIS' for e in record['result']['trace_events']))
        self.assertEqual(records['attach']['outcome']['open_loop']['decision'], 'ATTACH')
        self.assertEqual(records['create']['outcome']['open_loop']['decision'], 'CREATE')
        sensitive = records['sensitive']
        self.assertEqual(sensitive['outcome']['open_loop']['decision'], 'IGNORE')
        self.assertTrue(sensitive['outcome']['evidence']['sensitive'])
        self.assertFalse(any(e['agent'] == 'H-MEM' for e in sensitive['result']['trace_events']))
        self.assertEqual(len(load_recording('sensitive')['calls']), 1)
        self.assertEqual(records['surface']['result']['final_action'], 'SURFACE')
        self.assertEqual(records['restraint']['result']['final_action'], 'STAY_SILENT')
        self.assertEqual(records['revision']['result']['revision_count'], 1)
        self.assertEqual(records['revision']['result']['final_action'], 'SURFACE')
        self.assertTrue(records['duplicates']['check_ins'])
        events = records['attach']['result']['trace_events']
        self.assertTrue(any(e['agent'] == 'H-MEM' and e['action'] == 'QUERY' and e['detail']['hits'] for e in events))
        self.assertTrue(any(e['agent'] == 'H-MEM' and e['action'] == 'STORE' for e in events))

    def test_sample_reads_history_without_agents_or_canned_context_answers(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch('backend.app.bootstrap.build_orchestrator', side_effect=AssertionError('No agent should execute')), TestClient(app) as client:
            before = deepcopy(client.get('/open-loops').json())
            history = client.get('/api/sample/history').json()
            self.assertFalse(history['agents_executed'])
            self.assertFalse(history['model_calls'])
            self.assertTrue(history['records'])
            self.assertTrue(all(r['cached'] and r['provenance'] == 'recorded' for r in history['records']))
            self.assertEqual({c['case'] for c in client.get('/api/sample/cases').json()}, set(CASES))
            self.assertEqual(client.post('/api/sample/cases/unknown/replay').status_code, 404)
            self.assertEqual(client.get('/api/sample/cases/sensitive/image').status_code, 404)
            self.assertEqual(client.post('/api/screenshots', content=b'arbitrary').status_code, 501)
            self.assertEqual(client.post('/api/context/evaluate', json={'events': [{'context_type': 'CALENDAR', 'title': 'Unrecorded'}]}).status_code, 422)
            self.assertEqual(client.get('/open-loops').json(), before)
            notice = history['recall_views'][0]
            self.assertEqual(client.get(f"/notifications/{notice['notification_id']}").status_code, 200)
            self.assertEqual(client.get('/notifications').json()[0]['payload']['read'], True)

    def test_replay_endpoint_runs_real_agents_offline_and_does_not_touch_browsing_data(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch('socket.socket.connect', side_effect=AssertionError('No network')), TestClient(app) as client:
            before = deepcopy(client.get('/open-loops').json())
            for case, action in (('attach', 'STORED'), ('surface', 'SURFACE'), ('restraint', 'STAY_SILENT')):
                record = client.post(f'/api/sample/cases/{case}/replay').json()
                self.assertEqual((record['provenance'], record['workspace']), ('recorded', 'sample'))
                self.assertEqual(record['result']['final_action'], action)
                self.assertEqual(client.get(f"/api/runs/{record['run_id']}").json()['run_id'], record['run_id'])
            self.assertEqual(client.get('/open-loops').json(), before)

    def test_replay_changes_the_product_screens_and_reset_restores_them(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), TestClient(app) as client:
            baseline = {v['loop_id']: v['screenshot_count'] for v in client.get('/open-loops').json()}
            attach = client.post('/api/sample/cases/attach/replay').json()['outcome']['open_loop']['loop']['loop_id']
            after = {v['loop_id']: v['screenshot_count'] for v in client.get('/open-loops').json()}
            self.assertEqual(after[attach], baseline[attach] + 1)
            evidence = attach and client.post('/api/sample/cases/create/replay').json()['outcome']['evidence']
            self.assertEqual(client.get(evidence['image_url']).status_code, 200)
            client.post('/api/sample/cases/duplicates/replay')
            self.assertEqual(len(client.get('/api/check-ins').json()['questions']), 1)
            client.post('/api/sample/reset')
            self.assertEqual({v['loop_id']: v['screenshot_count'] for v in client.get('/open-loops').json()}, baseline)
            self.assertEqual(client.get('/api/check-ins').json()['questions'], [])

    def test_replayed_reminder_appears_as_an_unread_in_app_notification_and_never_as_a_system_one(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), TestClient(app) as client:
            before = len(client.get('/notifications').json())
            record = client.post('/api/sample/cases/surface/replay').json()
            notice = client.get(f"/notifications/{record['notification_id']}").json()
            self.assertFalse(notice['payload']['read'])
            self.assertIn('CACHED', notice['payload']['sources'])  # the browser raises no OS notification for these
            self.assertTrue(notice['payload']['reason'] and notice['payload']['evidence'])
            self.assertEqual(len(client.get('/notifications').json()), before + 1)
            self.assertIsNone(client.post('/api/sample/cases/restraint/replay').json().get('notification_id'))
            self.assertEqual(len(client.get('/notifications').json()), before)  # silence leaves nothing behind
            client.post('/api/sample/cases/surface/replay')
            client.post('/api/sample/reset')
            self.assertEqual(len(client.get('/notifications').json()), before)
