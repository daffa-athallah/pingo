"""Opt-in LIVE tests. Records use a dedicated fixture domain and are never agent evidence.

Normal offline discovery skips this class. Run through scripts/test_zetaris_repository.py.
Evidence fixtures remain append-only; the fixture loop ends INVALIDATED so it
does not appear among active hypotheses. No screenshot classification is run.
"""
from dataclasses import replace
import os
import unittest

from backend.app.adapters.zetaris import JdbcSettings, ZetarisError, ZetarisJdbc
from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.repositories.zetaris import ZetarisRepository


@unittest.skipUnless(os.environ.get('RUN_ZETARIS_INTEGRATION') == 'true', 'requires explicit live Zetaris opt-in')
class LiveRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = ZetarisJdbc(JdbcSettings.from_env()).connect()
        cls.repo = ZetarisRepository(cls.connection)

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.repo.get_open_loop('loop_repository_fixture_v1'):
                cls.repo.update_open_loop('loop_repository_fixture_v1', status=LoopStatus.INVALIDATED)
        finally:
            cls.connection.close()

    def test_persisted_fixture_graph_and_repository_contract(self):
        timestamp = '2026-10-25T00:00:00+00:00'
        domain = 'repository_integration_fixture'
        first = Entity('ent_repository_fixture_a_v1', 'test_fixture', domain, 'Synthetic repository fixture A', metadata={'fixture': 'true'})
        second = Entity('ent_repository_fixture_b_v1', 'test_fixture', domain, 'Synthetic repository fixture B', metadata={'fixture': 'true'})
        ev = Evidence('ev_repository_fixture_v1', 'integration_test_fixture', domain,
                      'Synthetic storage fixture; not extracted from a screenshot.', timestamp, False, 'high')
        links = [EvidenceEntity(ev.evidence_id, item.entity_id, 'test_fixture', 1.0) for item in (first, second)]
        self.repo.save_evidence(ev, [first, second], links)
        self.assertEqual(self.repo.get_evidence(ev.evidence_id), ev)
        self.repo.save_entity(first)
        self.repo.save_entity(second)
        self.assertEqual(self.repo.get_entities([first.entity_id, second.entity_id]), [first, second])
        self.repo.save_evidence(ev, [first, second], links)
        related = self.repo.get_related_evidence([first.entity_id], domain=domain)
        self.assertEqual(related, [ev])
        self.assertEqual(self.repo.get_related_evidence([first.entity_id], exclude_evidence_ids=[ev.evidence_id]), [])
        self.assertEqual(self.repo.get_related_entities([first.entity_id], domain=domain), [second])
        updated_entity = replace(first, metadata={'fixture': 'true', 'upsert': 'verified'})
        self.repo.save_entity(updated_entity)
        self.assertEqual(self.repo.get_entities([first.entity_id]), [updated_entity])
        hypothesis = OpenLoop('loop_repository_fixture_v1', 'Synthetic storage test hypothesis', domain,
                              LoopStatus.OPEN, 0.5, timestamp, timestamp)
        with self.repo.unit_of_work():
            self.repo.save_open_loop(hypothesis)
            self.repo.link_loop_entity(LoopEntity(hypothesis.loop_id, first.entity_id, 'test_fixture', 0.5))
        self.assertEqual(self.repo.get_open_loop(hypothesis.loop_id), hypothesis)
        edges = self.repo.get_loop_entities([hypothesis.loop_id])
        self.assertEqual(edges, [LoopEntity(hypothesis.loop_id, first.entity_id, 'test_fixture', 0.5)])
        self.repo.link_loop_entity(edges[0])
        self.assertEqual(self.repo.get_loop_entities([hypothesis.loop_id]), edges)
        self.assertIn(hypothesis, self.repo.get_candidate_open_loops([first.entity_id], domain=domain))
        self.assertIn(hypothesis, self.repo.get_active_open_loops(limit=1000))
        self.assertEqual(self.repo.get_related_evidence([edge.entity_id for edge in edges], domain=domain), [ev])
        updated = self.repo.update_open_loop(hypothesis.loop_id, title='Updated synthetic storage test', confidence=0.7)
        self.assertEqual(updated.title, 'Updated synthetic storage test')
        self.assertEqual(self.repo.get_evidence(ev.evidence_id), ev)

    def test_live_compensation_after_loop_link_failure(self):
        loop_id = 'loop_repository_compensation_fixture_v1'
        self.assertIsNone(self.repo.get_open_loop(loop_id))
        delegate = self.connection

        class FailOneLink:
            failed = False

            def query(self, sql, parameters=()):
                if not self.failed and sql.startswith('MERGE INTO recall_data.app.loop_entities'):
                    self.failed = True
                    raise ZetarisError('Deliberate integration-test link failure')
                return delegate.query(sql, parameters)

        repo = ZetarisRepository(FailOneLink())
        # Fixture entity is created here too, so test order is irrelevant.
        item = Entity('ent_repository_compensation_fixture_v1', 'test_fixture', 'repository_integration_fixture', 'Synthetic compensation fixture')
        repo.save_entity(item)
        hypothesis = OpenLoop(loop_id, 'Synthetic compensation test', item.domain, LoopStatus.OPEN, 0.5,
                              '2026-10-25T00:00:00+00:00', '2026-10-25T00:00:00+00:00')
        with self.assertRaises(ZetarisError):
            with repo.unit_of_work():
                repo.save_open_loop(hypothesis)
                repo.link_loop_entity(LoopEntity(loop_id, item.entity_id, 'test_fixture', 0.5))
        self.assertIsNone(repo.get_open_loop(loop_id))
        self.assertEqual(repo.get_loop_entities([loop_id]), [])
