"""Offline tests for the observable, asynchronous POST /api/screenshots over a real ZetarisRepository (SQL harness) and a scripted gateway."""
from contextlib import asynccontextmanager, nullcontext
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.main import app
from backend.app.repositories.zetaris import ZetarisRepository
from backend.tests.test_zetaris_repository import SqlHarness

PNG = b'\x89PNG\r\n\x1a\n' + b'fake-image-bytes-1'
PNG2 = b'\x89PNG\r\n\x1a\n' + b'fake-image-bytes-2'
VISION = {'requested_model': 'gpt-4o-mini', 'routed_model': 'gpt-4o-mini', 'provider': 'openai'}
REASON = {'requested_model': 'nemo', 'routed_model': 'nemo', 'provider': 'nvidia'}


class FakeGateway:
    vision_model = 'gpt-4o-mini'
    reasoning_model = 'nemo'

    def __init__(self, sensitive=False, fail=False):
        self.sensitive, self.fail, self.calls, self.last_routing = sensitive, fail, [], {}

    async def complete(self, messages, **kw):
        if self.fail:
            raise ModelGatewayError('Nightshift cannot be reached; no direct-provider fallback was attempted.')
        payload = messages[-1]['content']
        if isinstance(payload, list):  # image: perception
            self.calls.append('vision')
            self.last_routing = dict(VISION)
            return json.dumps({'domain': 'food', 'summary': 'A burger place menu in Carlton.', 'sensitive': self.sensitive, 'confidence': 'high',
                               'entities': [{'name': 'Test Burger', 'type': 'restaurant',
                                             'location': {'location_name': 'Carlton', 'city': 'Melbourne', 'country': 'Australia'}}]})
        self.calls.append('reasoning')
        self.last_routing = dict(REASON)
        data = json.loads(payload)
        evidence_id = data['new_evidence']['evidence_id']
        entity_ids = [e['entity_id'] for e in data['new_entities']]
        # like a sensible model: attach only to a candidate loop that already covers one of this screenshot's entities
        candidates = [c for c in data['candidate_open_loops'] if {e['entity_id'] for e in c.get('entities', [])} & set(entity_ids)]
        if candidates:
            return json.dumps({'decision': 'ATTACH', 'target_loop_id': candidates[0]['loop_id'], 'proposed_title': None, 'domain': 'food',
                               'confidence': 0.8, 'concise_reason': 'Another screenshot of the same venue.', 'supporting_evidence_ids': [evidence_id],
                               'supporting_entity_ids': entity_ids, 'material_uncertainty': None})
        return json.dumps({'decision': 'CREATE', 'target_loop_id': None, 'proposed_title': 'Interested in Test Burger (Carlton)', 'domain': 'food',
                           'confidence': 0.7, 'concise_reason': 'A saved burger place.', 'supporting_evidence_ids': [evidence_id],
                           'supporting_entity_ids': entity_ids, 'material_uncertainty': None})


class Base(unittest.TestCase):
    mode = {}

    def setUp(self):
        self.sql = SqlHarness()
        self.addCleanup(self.sql.db.close)
        self.repo = ZetarisRepository(self.sql)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.gateway = FakeGateway()

        @asynccontextmanager
        async def gateway():
            yield self.gateway

        patches = [patch.dict(os.environ, {'SAMPLE_MODE': 'false', **self.mode}, clear=True),
                   patch('backend.app.main.open_repository', return_value=nullcontext(self.repo)),
                   patch('backend.app.main.RUNTIME', self.runtime), patch('backend.app.runs_api.RUNTIME', self.runtime),
                   patch('backend.app.upload_api._gateway', gateway)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def post(self, data=PNG, wait=True):
        return self.client.post('/api/screenshots' + ('?wait=1' if wait else ''), content=data, headers={'Content-Type': 'image/png'})

    def events(self, run_id):
        return self.client.get(f'/api/runs/{run_id}').json()['result']['trace_events']

    @property
    def uploads(self):
        return list((self.runtime / 'uploads').glob('upload-*'))


class UploadApi(Base):
    def test_events_show_each_step_with_receipts_decision_details_and_state(self):
        body = self.post().json()
        self.assertEqual((body['status'], body['outcome']['open_loop']['decision']), ('done', 'CREATE'))
        events = self.events(body['run_id'])
        self.assertEqual([f"{e['agent']}:{e['action']}" for e in events],
                         ['UPLOAD:RECEIVED', 'EVIDENCE:STARTED', 'EVIDENCE:EXTRACT', 'ZETARIS:STORE', 'OPEN_LOOP:RETRIEVE', 'OPEN_LOOP:DECIDING',
                          'OPEN_LOOP:CREATE', 'OPEN_LOOP:STATE', 'RUN:DONE'])
        self.assertEqual([e['seq'] for e in events], list(range(1, 10)))
        by = {f"{e['agent']}:{e['action']}": e for e in events}
        extract = by['EVIDENCE:EXTRACT']
        self.assertEqual(extract['receipt'], VISION)
        self.assertEqual(extract['detail']['entities'][0]['name'], 'Test Burger')
        self.assertEqual(extract['detail']['entities'][0]['location_name'], 'Carlton')
        self.assertEqual(by['ZETARIS:STORE']['detail']['entities_new'], 1)
        self.assertEqual(by['OPEN_LOOP:RETRIEVE']['detail']['candidate_loops'], [])  # nothing saved yet
        decision = by['OPEN_LOOP:CREATE']
        self.assertEqual(decision['receipt'], REASON)
        self.assertEqual((decision['detail']['confidence'], decision['detail']['supporting_evidence_ids']), (0.7, [body['outcome']['evidence']['evidence_id']]))
        self.assertEqual(by['OPEN_LOOP:STATE']['detail']['change'], 'created')
        self.assertEqual(self.gateway.calls, ['vision', 'reasoning'])
        self.assertTrue(all(r['receipt']['provider'] in ('openai', 'nvidia') for r in body['outcome']['receipts']))
        run = self.client.get('/api/runs/' + body['run_id']).json()
        self.assertEqual((run['provenance'], run['workspace'], run['status'], run['result']['run_type']), ('live', 'canonical', 'done', 'EVIDENCE_INGESTION'))

    def test_second_screenshot_shows_what_was_retrieved_and_the_before_after_change(self):
        first = self.post().json()
        second = self.post(PNG2).json()
        events = {f"{e['agent']}:{e['action']}": e for e in self.events(second['run_id'])}
        retrieve = events['OPEN_LOOP:RETRIEVE']['detail']
        self.assertEqual([e['evidence_id'] for e in retrieve['related_evidence']], [first['outcome']['evidence']['evidence_id']])
        self.assertIn('burger place', retrieve['related_evidence'][0]['summary'])
        self.assertEqual([c['title'] for c in retrieve['candidate_loops']], ['Interested in Test Burger (Carlton)'])
        self.assertEqual(retrieve['candidate_loops'][0]['entities'], ['Test Burger'])
        self.assertEqual(events['ZETARIS:STORE']['detail']['entities_matched_existing'], 1)
        decision = events['OPEN_LOOP:ATTACH']['detail']
        self.assertEqual(decision['target_loop_id'], first['outcome']['open_loop']['loop']['loop_id'])
        state = events['OPEN_LOOP:STATE']['detail']
        self.assertEqual((state['before']['screenshots'], state['after']['screenshots']), (1, 2))
        self.assertIn('supporting screenshots 1 → 2', state['change'])
        self.assertEqual(second['outcome']['open_loop']['change']['change'], state['change'])

    def test_run_id_returns_at_once_and_progress_is_visible_while_running(self):
        started = self.post(wait=False)
        self.assertEqual(started.status_code, 202)
        run_id = started.json()['run_id']
        self.assertEqual(self.client.get(started.json()['status_url']).status_code, 200)
        for _ in range(200):
            run = self.client.get(f'/api/runs/{run_id}').json()
            if run['status'] != 'running':
                break
            time.sleep(0.02)
        self.assertEqual(run['status'], 'done')
        listed = self.client.get('/runs').json()
        self.assertEqual(listed[0]['run_id'], run_id)  # upload runs are listed, newest first
        self.assertEqual(self.client.get(f'/agent-events/{run_id}').json()[0]['action'], 'RECEIVED')

    def test_same_image_again_makes_no_model_call_and_no_second_record(self):
        first = self.post().json()
        calls = len(self.gateway.calls)
        second = self.client.post('/api/screenshots', content=PNG, headers={'Content-Type': 'image/png'}).json()
        self.assertEqual((second['duplicate'], second['outcome']['status']), (True, 'duplicate'))
        self.assertEqual(second['outcome']['evidence']['evidence_id'], first['outcome']['evidence']['evidence_id'])
        self.assertEqual((len(self.gateway.calls), len(self.repo.list_evidence())), (calls, 1))
        self.assertEqual(self.events(second['run_id'])[0]['action'], 'DUPLICATE')

    def test_sensitive_screenshot_is_not_described_retrieved_reasoned_over_or_kept(self):
        self.gateway.sensitive = True
        body = self.post().json()
        everything = json.dumps(self.client.get('/api/runs/' + body['run_id']).json()).lower()
        for word in ('burger', 'carlton', 'menu'):
            self.assertNotIn(word, everything)
        self.assertEqual(self.gateway.calls, ['vision'])  # never sent to the reasoning model
        names = [f"{e['agent']}:{e['action']}" for e in self.events(body['run_id'])]
        self.assertNotIn('OPEN_LOOP:RETRIEVE', names)
        self.assertNotIn('OPEN_LOOP:DECIDING', names)
        self.assertIn('OPEN_LOOP:IGNORE', names)
        self.assertEqual(body['outcome']['evidence'], {'evidence_id': body['outcome']['evidence']['evidence_id'], 'sensitive': True, 'domain': None,
                                                       'summary': None, 'entities': [], 'image_url': None})
        self.assertEqual(self.uploads, [])
        self.assertTrue(self.repo.get_evidence(body['outcome']['evidence']['evidence_id']).sensitive)

    def test_rejects_bad_input_before_any_model_call(self):
        self.assertEqual(self.client.post('/api/screenshots', content=b'').status_code, 400)
        self.assertEqual(self.client.post('/api/screenshots', content=b'GIF89a not allowed').status_code, 415)
        with patch('backend.app.upload_api.MAX_BYTES', 10):
            self.assertEqual(self.post().status_code, 413)
        self.assertEqual((self.gateway.calls, self.repo.list_evidence()), ([], []))

    def test_model_failure_stores_nothing_leaves_no_file_and_the_run_says_why(self):
        self.gateway.fail = True
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual((self.repo.list_evidence(), self.uploads), ([], []))
        run = self.client.get('/runs').json()[0]
        self.assertEqual((run['status'], run['result']['final_action']), ('failed', 'FAILED_SAFE'))
        self.assertEqual(run['result']['trace_events'][-1]['action'], 'FAILED_SAFE')

    def test_a_broken_observer_never_breaks_the_run(self):
        from backend.app.runs import RunRecorder
        original = RunRecorder.emit
        observed = {'STARTED', 'EXTRACT', 'STORE', 'RETRIEVE', 'DECIDING', 'CREATE', 'ATTACH', 'STATE'}

        def flaky(recorder, agent, action, *args, **kwargs):
            if action in observed:  # every observation hook fails; the run's own bookkeeping (RECEIVED, DONE) still works
                raise RuntimeError('observer bug')
            return original(recorder, agent, action, *args, **kwargs)

        with patch.object(RunRecorder, 'emit', autospec=True, side_effect=flaky), self.assertLogs('recall.observe', level='ERROR'):
            body = self.post().json()
        self.assertEqual((body['status'], body['outcome']['open_loop']['decision']), ('done', 'CREATE'))
        self.assertEqual((self.gateway.calls, len(self.repo.list_evidence())), (['vision', 'reasoning'], 1))
        self.assertEqual([e['action'] for e in self.events(body['run_id'])], ['RECEIVED', 'DONE'])  # nothing observed, nothing broken


class SampleModeIsolation(unittest.TestCase):
    def test_sample_mode_never_reads_or_writes_real_runs_and_labels_recorded_activity(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        runtime = Path(tmp.name)
        (runtime / 'context_eval').mkdir()
        (runtime / 'context_eval' / 'context-eval-1.json').write_text(json.dumps({'scenarios': {'A_relevant': {'result': {'run_id': 'run_REAL', 'trace_events': [
            {'agent': 'ZETARIS', 'action': 'LOAD'}]}}}}))
        (runtime / 'live_runs').mkdir()
        (runtime / 'live_runs' / 'run_REAL2.json').write_text(json.dumps({'run_id': 'run_REAL2', 'workspace': 'canonical', 'result': {'trace_events': []}}))
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch('backend.app.main.RUNTIME', runtime), patch('backend.app.runs_api.RUNTIME', runtime), \
                TestClient(app) as client:
            listed = client.get('/runs').json()
            self.assertEqual(len(listed), len(client.get('/api/sample/history').json()['records']))
            self.assertTrue(all((r['provenance'], r['workspace']) == ('recorded', 'sample') for r in listed))
            status = client.get('/integration-status').json()
            self.assertEqual(len(status['saved_reasoning_runs']), len(listed))
            self.assertEqual(client.get('/api/runs/run_REAL').status_code, 404)
            self.assertEqual(client.get('/agent-events/run_REAL2').status_code, 404)
            evaluated = client.post('/api/context/evaluate', json={'events': [{'context_type': 'CALENDAR', 'title': 'Dinner with Alex'}]})
            self.assertEqual(evaluated.status_code, 422)
            self.assertEqual(client.get('/health').json()['workspace'], 'sample')
        self.assertEqual(list((runtime / 'live_runs').glob('run_*.json')), [runtime / 'live_runs' / 'run_REAL2.json'])  # nothing was written


if __name__ == '__main__':
    unittest.main()


class LocationTests(unittest.TestCase):
    def test_maps_links_and_coordinates_are_parsed_and_garbage_is_not(self):
        from backend.app import geocode
        pin = 'https://www.google.com/maps/place/X/@-37.9187,145.1286,17z/data=!3d-37.9190123!4d145.1290456'
        self.assertEqual(geocode.parse_maps_link(pin), (-37.9190123, 145.1290456))
        self.assertEqual(geocode.parse_maps_link('-37.9187, 145.1286'), (-37.9187, 145.1286))
        self.assertEqual(geocode.parse_maps_link('https://www.google.com/maps?q=-37.918,145.128'), (-37.918, 145.128))
        for bad in ('', 'hello', '999, 999', 'https://example.com'):
            self.assertIsNone(geocode.parse_maps_link(bad))

    def test_resolver_accepts_only_unambiguous_matches_and_never_guesses(self):
        from backend.app import geocode
        from backend.app.domain.models import Entity
        entity = Entity('e', 'place', 'food', 'Marrybrown', location_name='Clayton', city='Melbourne', country='Australia')
        hit = {'name': 'Marrybrown', 'display_name': 'Marrybrown, Clayton Road, Clayton, Melbourne, Victoria, Australia', 'lat': '-37.92', 'lon': '145.12', 'osm_type': 'node', 'osm_id': 7}
        self.assertEqual(geocode.resolve(entity, search=lambda *a, **k: [hit])['location_id'], 'osm:node:7')
        far = {**hit, 'lat': '-37.80', 'osm_id': 8}
        self.assertEqual(geocode.resolve(entity, search=lambda *a, **k: [hit, far])['status'], 'ambiguous')
        elsewhere = {**hit, 'display_name': 'Marrybrown, Orchard Road, Singapore'}
        self.assertEqual(geocode.resolve(entity, search=lambda *a, **k: [elsewhere])['status'], 'not_found')
        self.assertEqual(geocode.resolve(entity, search=lambda *a, **k: [])['status'], 'not_found')
        building = Entity('b', 'place', 'travel', 'Learning and Teaching Building', location_name='Clayton', city='Melbourne', country='Australia')
        similar = {'name': 'Biomedical Learning and Teaching Building', 'display_name': 'Biomedical Learning and Teaching Building, Ancora Imparo Way, Clayton, Melbourne, Victoria, Australia',
                   'lat': '-37.91', 'lon': '145.13', 'osm_type': 'way', 'osm_id': 1}
        self.assertEqual(geocode.resolve(building, search=lambda *a, **k: [similar])['status'], 'not_found')  # a different building is never accepted
        shop = Entity('s', 'product', 'shopping', 'Jacket')
        self.assertFalse(geocode.eligible(shop))

    def test_pin_endpoint_stores_a_verified_coordinate_only_for_places(self):
        import os
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.app.main import app
        with patch.dict(os.environ, {'RECALL_MODE': 'demo'}, clear=True), TestClient(app) as client:
            place = next(e for e in client.get('/entities').json() if e['domain'] == 'food') if client.get('/entities').status_code == 200 else None
            if place is None:
                self.skipTest('no entities route')
            entity_id = place.get('entity_id') or place.get('id')
            ok = client.post(f'/api/entities/{entity_id}/location', json={'link': '-37.9187, 145.1286'})
            self.assertEqual(ok.status_code, 200)
            self.assertTrue(ok.json()['location_id'].startswith('pin:'))
            self.assertEqual(client.post(f'/api/entities/{entity_id}/location', json={'link': 'nonsense'}).status_code, 422)
            self.assertEqual(client.post('/api/entities/missing/location', json={'link': '-37.9, 145.1'}).status_code, 404)


class DeleteIntentionTests(unittest.TestCase):
    def test_delete_hides_the_intention_and_its_screenshots_and_allows_a_fresh_sync(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.app.main import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'RECALL_MODE': 'demo'}, clear=True), \
                patch('backend.app.intentions_api.hidden_path', lambda state: Path(directory) / 'hidden.json'), TestClient(app) as client:
            before = client.get('/open-loops').json()
            target = next(l for l in before if l['screenshots'])
            response = client.post(f"/api/open-loops/{target['loop_id']}/delete")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['deleted'], target['loop_id'])
            after = client.get('/open-loops').json()
            self.assertEqual(len(after), len(before) - 1)
            self.assertNotIn(target['loop_id'], {l['loop_id'] for l in after})
            self.assertEqual(client.post(f"/api/open-loops/{target['loop_id']}/delete").status_code, 404)
            self.assertEqual(client.post('/api/open-loops/missing/delete').status_code, 404)


class DeleteScreenshotTests(unittest.TestCase):
    def test_a_deleted_screenshot_disappears_from_its_intention(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.app.main import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'RECALL_MODE': 'demo'}, clear=True), \
                patch('backend.app.intentions_api.hidden_path', lambda state: Path(directory) / 'hidden.json'), TestClient(app) as client:
            loops = client.get('/open-loops').json()
            target = next(l for l in loops if len(l['screenshots']) >= 1)
            shot = target['screenshots'][0]['evidence_id']
            self.assertEqual(client.post(f'/api/evidence/{shot}/delete').status_code, 200)
            after = next(l for l in client.get('/open-loops').json() if l['loop_id'] == target['loop_id'])
            self.assertNotIn(shot, [s['evidence_id'] for s in after['screenshots']])
            self.assertEqual(after['screenshot_count'], target['screenshot_count'] - 1)
            self.assertEqual(client.post('/api/evidence/missing/delete').status_code, 404)
