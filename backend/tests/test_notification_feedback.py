"""Offline fixtures exercise real feedback parsing/persistence, not live model proof."""
import asyncio
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.context.routes import router
from backend.app.context.service import ContextConflict, ContextService
from backend.app.domain.models import LoopStatus
from backend.app.repositories.context_store import Notification
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.app.repositories.zetaris import ZetarisRepository
from backend.tests.test_context_notifications import NOW, MODEL, seed
from backend.tests.test_zetaris_repository import SqlHarness


class FeedbackGateway:
    reasoning_model = MODEL

    def __init__(self, *replies, receipt=True, hook=None):
        self.replies, self.calls, self.last_routing = list(replies), [], {}
        self.receipt, self.hook = receipt, hook

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def complete(self, messages, **kwargs):
        payload = json.loads(messages[-1]['content'])
        self.calls.append(payload)
        if self.hook:
            self.hook()
        result = self.replies.pop(0)
        if isinstance(result, Exception):
            raise result
        self.last_routing = {'requested_model': MODEL, 'routed_model': MODEL, 'provider': 'nvidia'} if self.receipt else {}
        return json.dumps(result)


def reply(decision='KEEP', **kw):
    return dict(decision=decision, loop_id='loop_test', proposed_title='Saved restaurant inspiration' if decision == 'REVISE' else None,
                concise_reason='Explicit offline feedback fixture.', supporting_evidence_ids=['ev_0'], **kw)


def notice(repo):
    seed(repo)
    item = Notification('notice_test', 'loop_test', NOW.isoformat(), {
        'title': 'A place you saved', 'message': 'Remember this place?', 'reason': 'Fixture context.',
        'context_ids': [], 'trigger_types': ['LOCATION'], 'delivery_status': 'APPROVED',
        'read': False, 'dismissed': False, 'feedback': None, 'feedback_events': [], 'snoozed_until': None})
    repo.save_notification(item)
    return item


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict('os.environ', {'SAMPLE_MODE': 'false'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.repo = InMemoryLoopRepository()
        notice(self.repo)

    def service(self, *responses, **kw):
        self.gateway = FeedbackGateway(*responses, **kw)
        return ContextService(self.repo, gateway_factory=lambda: self.gateway, clock=lambda: NOW)

    async def test_feedback_persisted_before_real_agent_method_and_revision(self):
        def saved_first():
            n = self.repo.get_notification('notice_test')
            self.assertEqual(n.payload['feedback'], 'NOT_RELEVANT')
            self.assertEqual(n.payload['feedback_review']['state'], 'RUNNING')
        service = self.service(reply('REVISE'), hook=saved_first)
        before = dict(self.repo.evidence)
        result = await service.action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'COMPLETED')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Saved restaurant inspiration')
        self.assertEqual(self.repo.evidence, before)
        self.assertEqual(len(self.repo.loops), 1)
        payload = self.gateway.calls[0]
        self.assertEqual(payload['feedback']['action'], 'NOT_RELEVANT')
        self.assertEqual(len(payload['supporting_evidence']), 3)
        self.assertEqual(len(payload['entities']), 3)
        self.assertTrue(result['payload']['feedback_review']['trace_events'][-1]['receipt'])

    async def test_done_direct_authority_and_agent_receipt(self):
        service = self.service(reply('RESOLVE'))
        result = await service.action('notice_test', 'DONE')
        self.assertEqual(result['payload']['feedback_review']['state'], 'COMPLETED')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.RESOLVED)
        self.assertEqual(self.gateway.calls[0]['open_loop']['status'], 'RESOLVED')

    async def test_inspiration_can_make_dormant(self):
        result = await self.service(reply('DORMANT')).action('notice_test', 'JUST_INSPIRATION')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.DORMANT)
        self.assertEqual(result['payload']['feedback_events'][-1]['agent_review']['state'], 'COMPLETED')

    async def test_snooze_keeps_active_and_suppresses_notifications(self):
        service = self.service(reply())
        await service.action('notice_test', 'SNOOZE')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.ACTIVE)
        self.assertEqual(service._blocked('loop_test'), 'snoozed')
        self.assertEqual(service.list_notifications(), [])

    async def test_duplicate_and_poll_do_not_repeat_model_calls(self):
        service = self.service(reply())
        first, second = await asyncio.gather(service.action('notice_test', 'NOT_RELEVANT'), service.action('notice_test', 'NOT_RELEVANT'))
        self.assertEqual(first, second)
        for _ in range(3): service.list_notifications()
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(len(first['payload']['feedback_events']), 1)
        with self.assertRaises(ContextConflict):
            await service.action('notice_test', 'DONE')

    async def test_dismiss_read_delivered_do_not_call_agent(self):
        service = self.service()
        for action in ('DELIVERED', 'READ', 'DISMISS'):
            await service.action('notice_test', action)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.ACTIVE)

    async def test_transient_failure_retries_once(self):
        result = await self.service(OSError('fixture'), reply()).action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(len(self.gateway.calls), 2)
        self.assertEqual(result['payload']['feedback_review']['state'], 'COMPLETED')
        self.assertEqual(result['payload']['feedback_review']['trace_events'][1]['action'], 'RETRY')

    async def test_failure_preserves_feedback_and_done_never_reopens(self):
        service = self.service(OSError('private fixture'), OSError('private fixture'))
        result = await service.action('notice_test', 'DONE')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.RESOLVED)
        self.assertEqual(result['payload']['feedback'], 'DONE')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
        self.assertNotIn('private fixture', json.dumps(result))
        self.assertEqual(await service.action('notice_test', 'DONE'), result)
        self.assertEqual(len(self.gateway.calls), 2)

    async def test_unsafe_decisions_cannot_modify_other_loops_or_user_intent(self):
        for mutation in ({'loop_id': 'other'}, {'decision': 'CREATE'}, {'decision': 'RESOLVE'},
                         {'supporting_evidence_ids': ['made_up']}, {'proposed_title': 'Invalid for KEEP'}):
            self.repo = InMemoryLoopRepository(); notice(self.repo)
            bad = {**reply(), **mutation}
            result = await self.service(bad, bad).action('notice_test', 'NOT_RELEVANT')
            self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
            self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.ACTIVE)

    async def test_unverified_receipt_cannot_apply(self):
        result = await self.service(reply('REVISE'), reply('REVISE'), receipt=False).action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Test saved intention')

    async def test_snooze_cannot_be_reinterpreted_as_completion(self):
        result = await self.service(reply('RESOLVE'), reply('RESOLVE')).action('notice_test', 'SNOOZE')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.ACTIVE)
        self.assertIsNotNone(result['payload']['snoozed_until'])

    async def test_slow_review_is_bounded_and_feedback_survives(self):
        service = self.service(reply())
        async def slow(*args, **kw):
            await asyncio.sleep(1)
        self.gateway.complete = slow
        from backend.app import aio
        timeout = aio.timeout
        with patch('backend.app.aio.timeout', side_effect=lambda seconds: timeout(.01)):
            result = await service.action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback'], 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')

    async def test_no_evidence_never_calls_model(self):
        self.repo.evidence.clear()
        result = await self.service().action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'SKIPPED')
        self.assertEqual(self.gateway.calls, [])

    async def test_sql_failed_review_write_compensates_intention_update(self):
        sql = SqlHarness(); self.addCleanup(sql.db.close)
        sql.db.executescript('CREATE TABLE context_evaluations (evaluation_id TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT); CREATE TABLE notifications (notification_id TEXT PRIMARY KEY, loop_id TEXT, created_at TEXT, payload_json TEXT);')
        self.repo = ZetarisRepository(sql); notice(self.repo)
        def fail_review_save():
            sql.failures.append(lambda query: query.startswith('MERGE INTO recall_data.app.notifications'))
        result = await self.service(reply('REVISE'), hook=fail_review_save).action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Test saved intention')
        self.assertEqual(self.repo.get_notification('notice_test').payload['feedback'], 'NOT_RELEVANT')

    async def test_sensitive_graph_never_sent(self):
        self.repo.evidence['ev_0'] = replace(self.repo.evidence['ev_0'], sensitive=True)
        result = await self.service().action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'SKIPPED')
        self.assertEqual(self.gateway.calls, [])

    async def test_changed_loop_is_not_overwritten(self):
        def change():
            self.repo.update_open_loop('loop_test', title='Newer intention')
        result = await self.service(reply('REVISE'), hook=change).action('notice_test', 'NOT_RELEVANT')
        self.assertEqual(result['payload']['feedback_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Newer intention')

    async def test_sample_without_models_stays_offline(self):
        with patch.dict('os.environ', {'SAMPLE_MODE': 'true', 'METERLESS_BASE_URL': ''}):
            result = await self.service().action('notice_test', 'DONE')
        self.assertEqual(result['payload']['feedback_review']['state'], 'RECORDED')
        self.assertEqual(self.gateway.calls, [])

    async def test_sql_repository_persists_review_without_new_tables(self):
        sql = SqlHarness(); self.addCleanup(sql.db.close)
        sql.db.executescript('CREATE TABLE context_evaluations (evaluation_id TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT); CREATE TABLE notifications (notification_id TEXT PRIMARY KEY, loop_id TEXT, created_at TEXT, payload_json TEXT);')
        self.repo = ZetarisRepository(sql); notice(self.repo)
        result = await self.service(reply('REVISE')).action('notice_test', 'NOT_RELEVANT')
        loaded = ZetarisRepository(sql)
        self.assertEqual(loaded.get_notification('notice_test').payload, result['payload'])
        self.assertEqual(loaded.get_open_loop('loop_test').title, 'Saved restaurant inspiration')

    async def test_http_endpoint_returns_persisted_review(self):
        app = FastAPI(); app.include_router(router)
        app.state.repository = self.repo
        app.state.context_service = self.service(reply('DORMANT'))
        with TestClient(app) as client:
            response = client.post('/notifications/notice_test/actions', json={'action': 'JUST_INSPIRATION'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['payload']['feedback_review']['decision']['decision'], 'DORMANT')
