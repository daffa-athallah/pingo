import asyncio
import os
import sys
import unittest
from unittest.mock import patch

from backend.app.bootstrap import build_orchestrator, open_repository
from backend.app.domain.models import LoopEntity, LoopStatus, OpenLoop
from backend.app.sample import run_sample
from backend.tests.test_zetaris_repository import SqlHarness, entity
from backend.app.repositories.zetaris import ZetarisRepository
from backend.app.agents.open_loop import Decision, LoopDecision
from backend.app.adapters.zetaris import ZetarisError


class BootstrapTests(unittest.TestCase):
    def test_sample_repository_needs_no_jdbc_dependencies_or_credentials(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch.dict(sys.modules, {'jaydebeapi': None, 'jpype': None}):
            with open_repository() as repository:
                self.assertEqual(type(repository).__name__, 'InMemoryLoopRepository')

    def test_missing_production_configuration_fails_without_sample_fallback(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'false'}, clear=True):
            with self.assertRaisesRegex(ZetarisError, 'ZETARIS_JDBC_URL'):
                with open_repository():
                    self.fail('Production must not silently fall back to fixtures.')

    def test_deterministic_sample_runs_without_external_network(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
            first = asyncio.run(run_sample())
            second = asyncio.run(run_sample())
        self.assertEqual(first, second)
        self.assertEqual(first['mode'], 'sample')
        self.assertFalse(first['model_calls'])
        self.assertEqual(first['result']['final_action'], 'SURFACE')
        self.assertEqual([event['agent'] for event in first['result']['trace_events']], ['CONTEXT', 'CRITIC'])
        self.assertTrue(all(event['receipt'] is None for event in first['result']['trace_events']))

    def test_sample_requires_explicit_mode(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'false'}, clear=True):
            with self.assertRaises(RuntimeError):
                asyncio.run(run_sample())

    def test_composition_compensates_existing_apply_without_changing_agent_code(self):
        sql = SqlHarness()
        self.addCleanup(sql.db.close)
        repository = ZetarisRepository(sql)
        repository.save_entity(entity())
        orchestrator = build_orchestrator(object(), repository, new_loop_id=lambda: 'loop_failure')
        decision = LoopDecision(Decision.CREATE, None, 'Synthetic test', 'food', 0.5, 'Synthetic fixture',
                                ['ev_fixture'], ['ent_1'])
        sql.failures = [lambda statement: statement.startswith('MERGE INTO recall_data.app.loop_entities')]
        with self.assertRaises(ZetarisError):
            orchestrator.open_loop_agent.apply(decision)
        self.assertIsNone(repository.get_open_loop('loop_failure'))
        self.assertEqual(repository.get_loop_entities(['loop_failure']), [])
