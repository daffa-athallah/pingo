"""H-MEM integration. Two groups:

  * logic tests against a small stand-in server speaking the sidecar's protocol (fast, no Node): they prove what Recall does with a memory engine
    (what is remembered, what is never remembered, how hits reach the agent, what happens when the engine is down);
  * RealEngine tests that start the vendored Meterless H-MEM reference implementation (engines/hmem/server.ts) with Node and use IT:
    they prove the actual engine finds the earlier Elmo's screenshots that entity-ID retrieval misses.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.app.demo_workspace import open_demo_repository
from backend.app.domain.models import Entity, Evidence, EvidenceEntity
from backend.app.hmem import HMemClient, HMemError, HMemRepository, memory_from_evidence, seed_from_repository
from backend.tests.test_upload_api import Base, PNG

ROOT = Path(__file__).resolve().parents[2]
TOKEN = re.compile(r'[a-z0-9]+')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class StandInEngine:
    """Implements the sidecar protocol with a crude token-overlap ranking. NOT H-MEM; it only lets the integration logic be tested quickly."""

    def __init__(self):
        self.memories, self.queries, self.ledger = [], [], []
        engine = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == '/health':
                    return self._send(200, {'ok': True, 'records': len(engine.memories), 'ledger': len(engine.ledger)})
                if self.path == '/refs':
                    return self._send(200, {'refs': [r for m in engine.memories for r in m['provenance'].get('refs', [])]})
                if self.path.startswith('/ledger'):
                    return self._send(200, {'total': len(engine.ledger), 'stats': {}, 'entries': engine.ledger})
                self._send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('content-length', 0))) or b'{}')
                if self.path == '/memories':
                    record = {**body, 'id': f'mem-{len(engine.memories) + 1}', 'domain': (body.get('tags') or ['general'])[0], 'entities': [],
                              'layer': body.get('layer', 'working'), 'confidence': body.get('confidence', 0.7)}
                    engine.memories.append(record)
                    engine.ledger.append({'memoryId': record['id'], 'action': 'create'})
                    return self._send(201, record)
                if self.path == '/query':
                    engine.queries.append(body['query'])
                    q = set(TOKEN.findall(body['query'].lower()))
                    ranked = []
                    for m in engine.memories:
                        t = set(TOKEN.findall(m['content'].lower()))
                        score = len(q & t) / max(len(q | t), 1) * m['confidence'] * 2
                        if score >= body.get('threshold', 0.35):
                            ranked.append({**m, 'relevance': score})
                    ranked.sort(key=lambda m: -m['relevance'])
                    return self._send(200, {'memories': ranked[:body.get('topN', 5)], 'trace': {'strategy': 'standin'}, 'context': ''})
                if self.path == '/reset':
                    engine.memories.clear()
                    return self._send(200, {'ok': True})
                self._send(404, {})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


ELMOS_VARIANT = 'The screenshot shows information about Elmo\'s Hamburger, a restaurant in Fitzroy North, Melbourne, known for its smashed cheeseburgers and thick shakes.'


def new_elmos(repository):
    """A screenshot whose entity ('Elmo's Hamburger') has a DIFFERENT id from the saved 'Elmo's Hamburger Restaurant' entities."""
    entity = Entity('ent_new_elmos', 'restaurant', 'food', "Elmo's Hamburger", city='Melbourne')
    evidence = Evidence('ev_new_elmos', 'screenshot', 'food', ELMOS_VARIANT, '2026-10-26T12:00:00+00:00', False, 'high', 'upload-x.png')
    return evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', 0.9)]


class Memory(unittest.TestCase):
    def test_what_is_remembered_and_what_never_is(self):
        repo = open_demo_repository()
        evidence = repo.list_evidence()[0]
        entities = repo.get_entities([k.entity_id for k in repo.get_evidence_entities([evidence.evidence_id])])
        record = memory_from_evidence(evidence, entities)
        self.assertEqual(record['provenance']['refs'], [f'evidence:{evidence.evidence_id}'])
        self.assertEqual((record['type'], record['confidence']), ('factual', 0.9 if evidence.confidence == 'high' else record['confidence']))
        self.assertIn(entities[0].name, record['content'])
        self.assertIsNone(memory_from_evidence(replace(evidence, sensitive=True), entities))  # sensitive Evidence is never remembered

    def test_client_reports_an_unreachable_engine_as_an_error_not_a_crash(self):
        client = HMemClient(f'http://127.0.0.1:{free_port()}', timeout=0.5)
        self.assertIsNone(client.health())
        with self.assertRaises(HMemError):
            client.query('anything')


class Integration(unittest.TestCase):
    def setUp(self):
        self.engine = StandInEngine()
        self.addCleanup(self.engine.close)
        self.client = HMemClient(self.engine.url)
        self.repo = open_demo_repository()
        self.events = []

    def test_seeding_is_idempotent(self):
        first = seed_from_repository(self.client, self.repo)
        again = seed_from_repository(self.client, self.repo)
        self.assertEqual((first['added'], again['added'], again['already_present']), (30, 0, 30))
        self.assertTrue(all(m['layer'] == 'long_term' for m in self.engine.memories))  # established history

    def test_memory_finds_evidence_that_entity_links_miss_and_the_agent_receives_it(self):
        seed_from_repository(self.client, self.repo)
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, self.client, listener=lambda kind, payload: self.events.append((kind, payload)))
        self.assertEqual(self.repo.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[evidence.evidence_id]), [])  # entity links: nothing
        proxy.save_evidence(evidence, entities, links)
        related = proxy.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[evidence.evidence_id])
        found = {e.evidence_id for e in related}
        self.assertTrue(found, 'memory should surface the earlier Elmo\'s screenshots')
        self.assertTrue(any("elmo" in self.repo.get_evidence(i).summary.lower() for i in found))  # the stand-in ranks crudely; the real engine is tested below
        self.assertNotIn(evidence.evidence_id, found)  # a screenshot never retrieves itself
        kinds = [k for k, _ in self.events]
        self.assertEqual(kinds[:2], ['query', 'stored'])  # asked first, remembered after
        self.assertIn('merged', kinds)
        self.assertEqual(self.engine.memories[-1]['provenance']['refs'], [f'evidence:{evidence.evidence_id}'])

    def test_sensitive_evidence_is_neither_queried_nor_remembered(self):
        seed_from_repository(self.client, self.repo)
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, self.client, listener=lambda kind, payload: self.events.append((kind, payload)))
        before = (len(self.engine.memories), len(self.engine.queries))
        proxy.save_evidence(replace(evidence, sensitive=True), entities, links)
        self.assertEqual((len(self.engine.memories), len(self.engine.queries), self.events), (before[0], before[1], []))
        self.assertEqual(proxy.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[evidence.evidence_id]), [])

    def test_memory_hits_respect_domain_exclusions_and_limit(self):
        seed_from_repository(self.client, self.repo)
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, self.client)
        proxy.save_evidence(evidence, entities, links)
        everything = proxy.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[evidence.evidence_id])
        self.assertEqual(proxy.get_related_evidence([entities[0].entity_id], domain='shopping'), [])
        self.assertEqual(len(proxy.get_related_evidence([entities[0].entity_id], limit=1)), 1)
        excluded = proxy.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[everything[0].evidence_id, evidence.evidence_id])
        self.assertNotIn(everything[0].evidence_id, {e.evidence_id for e in excluded})

    def test_a_memory_pointing_at_missing_evidence_is_dropped(self):
        self.client.add({'content': ELMOS_VARIANT, 'source': 'screenshot:ghost', 'type': 'factual', 'confidence': 0.9, 'tags': ['food'],
                         'provenance': {'origin': 'file_save', 'learnedAt': 0, 'label': 'ghost', 'refs': ['evidence:ev_does_not_exist']}})
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, self.client)
        proxy.save_evidence(evidence, entities, links)
        self.assertEqual(proxy.hits, [])

    def test_engine_down_means_entity_links_only_and_the_run_says_so(self):
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, HMemClient(f'http://127.0.0.1:{free_port()}', timeout=0.5),
                               listener=lambda kind, payload: self.events.append((kind, payload)))
        proxy.save_evidence(evidence, entities, links)
        self.assertEqual([k for k, _ in self.events], ['unavailable'])
        self.assertFalse(proxy.available)
        self.assertEqual(proxy.get_related_evidence([entities[0].entity_id]), self.repo.get_related_evidence([entities[0].entity_id]))
        self.assertIsNotNone(self.repo.get_evidence(evidence.evidence_id))  # the Evidence itself was stored regardless


class UploadWithMemory(Base):
    """The upload run shows the memory steps, and the agent receives what memory found."""

    def setUp(self):
        super().setUp()
        self.engine = StandInEngine()
        self.addCleanup(self.engine.close)
        self.client.app.state.hmem = HMemClient(self.engine.url)  # the client's own app: another test reloads the main module
        self.engine.memories.append({'id': 'mem-0', 'content': 'The first screenshot showed Test Burger, a burger place in Carlton. Entities: Test Burger.', 'source': 'screenshot:a.png',
                                     'type': 'factual', 'layer': 'long_term', 'confidence': 0.9, 'domain': 'food', 'entities': [], 'tags': ['food'],
                                     'provenance': {'origin': 'file_save', 'learnedAt': 0, 'label': 'Saved screenshot', 'refs': []}})

    def test_events_and_ledger_for_a_run_with_memory(self):
        first = self.post().json()
        engine_evidence = first['outcome']['evidence']['evidence_id']
        self.engine.memories[0]['provenance']['refs'] = [f'evidence:{engine_evidence}']
        second = self.post(PNG + b'2').json()
        events = self.events(second['run_id'])
        names = [f"{e['agent']}:{e['action']}" for e in events]
        stored = next(i for i, n in enumerate(names) if n.endswith(':STORE') and not n.startswith('H-MEM'))
        self.assertGreater(names.index('H-MEM:QUERY'), stored)  # memory is asked after the Evidence is stored, never before
        self.assertLess(names.index('H-MEM:STORE'), names.index('OPEN_LOOP:RETRIEVE'))
        query = next(e for e in events if e['action'] == 'QUERY')['detail']
        self.assertTrue(query['hits'])
        retrieve = next(e for e in events if e['action'] == 'RETRIEVE')['detail']
        self.assertTrue(all('via' in item for item in retrieve['related_evidence']))
        self.assertEqual(self.client.get('/health').json()['hmem']['enabled'], True)
        self.assertEqual(self.client.get('/api/memory/ledger').status_code, 200)


TSX = ROOT / 'engines/hmem/node_modules/.bin/tsx'


@unittest.skipIf(os.environ.get('RECALL_SKIP_REAL_HMEM') == '1', 'RECALL_SKIP_REAL_HMEM=1')
@unittest.skipUnless(shutil.which('node') and TSX.exists(), 'run `npm ci --ignore-scripts` in engines/hmem (Node 20+) to enable the real-engine tests')
class RealEngine(unittest.TestCase):
    """Starts engines/hmem/server.ts (the unmodified Meterless H-MEM reference implementation) and uses it."""

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.process = subprocess.Popen([str(TSX), 'server.ts'], cwd=ROOT / 'engines/hmem', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       env={**os.environ, 'HMEM_PORT': str(cls.port), 'HMEM_ALLOW_RESET': '1', 'HMEM_PERSIST_DIR': ''})
        cls.client = HMemClient(f'http://127.0.0.1:{cls.port}', timeout=10)
        for _ in range(100):
            if cls.client.health():
                return
            time.sleep(0.1)
        cls.process.kill()
        raise RuntimeError('The H-MEM sidecar did not start.')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)

    def setUp(self):
        self.client.reset()
        self.repo = open_demo_repository()

    def test_the_real_engine_finds_the_elmos_screenshots_that_entity_links_miss(self):
        seed_from_repository(self.client, self.repo)
        evidence, entities, links = new_elmos(self.repo)
        self.assertEqual(self.repo.get_related_evidence([entities[0].entity_id]), [])  # what the agent got before H-MEM
        proxy = HMemRepository(self.repo, self.client)
        proxy.save_evidence(evidence, entities, links)
        found = [self.repo.get_evidence(h['evidence_id']) for h in proxy.hits]
        self.assertGreaterEqual(len(found), 3)
        self.assertTrue(any("elmo" in e.summary.lower() for e in found))
        self.assertTrue(all(h['relevance'] >= 0.35 for h in proxy.hits))  # H-MEM's own threshold
        related = proxy.get_related_evidence([entities[0].entity_id], exclude_evidence_ids=[evidence.evidence_id])
        self.assertTrue({h['evidence_id'] for h in proxy.hits} & {e.evidence_id for e in related})

    def test_the_engine_keeps_provenance_confidence_and_an_audit_ledger(self):
        seed_from_repository(self.client, self.repo)
        evidence, entities, links = new_elmos(self.repo)
        proxy = HMemRepository(self.repo, self.client)
        proxy.save_evidence(evidence, entities, links)
        ledger = self.client.ledger(limit=500)
        self.assertGreaterEqual(ledger['stats'].get('create', 0), 31)  # 30 seeded + this screenshot
        self.assertGreaterEqual(ledger['stats'].get('read', 0), 1)  # the query itself is audited
        entry = next(e for e in ledger['entries'] if e['memoryId'] == proxy.memory_id and e['action'] == 'create')
        self.assertEqual(entry['newState']['provenance']['refs'], [f'evidence:{evidence.evidence_id}'])
        self.assertTrue(0 < entry['newState']['confidence'] <= 1)

    def test_a_record_without_a_source_is_rejected_by_construction(self):
        with self.assertRaises(HMemError):
            self.client.add({'content': 'no source', 'source': ' '})

    def test_seeding_the_real_engine_is_idempotent(self):
        self.assertEqual(seed_from_repository(self.client, self.repo)['added'], 30)
        self.assertEqual(seed_from_repository(self.client, self.repo)['added'], 0)


if __name__ == '__main__':
    unittest.main()
