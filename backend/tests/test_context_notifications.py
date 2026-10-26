"""Offline contract tests: scripted model responses are TEST FIXTURES, not real model proof."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.app.context.contracts import ContextInput, EvaluationInput
from backend.app.context.geography import distance_meters
from backend.app.context.service import ContextConflict, ContextService
from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.main import app
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.app.repositories.zetaris import ZetarisRepository
from backend.tests.test_zetaris_repository import SqlHarness

NOW = datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)
MODEL = 'nvidia/nemotron-3-ultra-550b-a55b'


class ScriptedGateway:
    """Explicit offline fixture. Uses real Context/Critic parsers and orchestrator branches."""
    reasoning_model = MODEL
    def __init__(self, decisions=('MATCH', 'SURFACE'), receipts=True):
        self.decisions, self.calls, self.last_routing = list(decisions), [], {}
        self.receipts = receipts
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def complete(self, messages, **kwargs):
        self.calls.append(json.loads(messages[-1]['content']))
        kind = self.decisions.pop(0)
        if isinstance(kind, Exception):
            raise kind
        self.last_routing = {'requested_model': MODEL, 'routed_model': MODEL, 'provider': 'nvidia'} if self.receipts else {}
        data = self.calls[-1]
        if 'candidate_open_loops' in data:
            loop = data['candidate_open_loops'][0]['loop_id']
            ctx = data['context_events'][-1]
            return json.dumps(dict(decision=kind, candidate_loop_id=None if kind == 'NO_MATCH' else loop,
                trigger_type=None if kind == 'NO_MATCH' else ctx['context_type'], relevant_context_ids=[] if kind == 'NO_MATCH' else [ctx['context_id']],
                relevance_confidence=.9, concise_reason='Offline context fixture.', material_uncertainty=None, verification_request=None))
        return json.dumps(dict(decision=kind, loop_id=data['open_loop']['loop_id'], confidence=.9, concise_reason='Offline critic fixture.',
            supporting_evidence_ids=[e['evidence_id'] for e in data['supporting_evidence']], supporting_context_ids=[e['context_id'] for e in data['context_events']],
            material_uncertainty='Uncertain timing.' if kind == 'ASK' else None, question='Is this still relevant?' if kind == 'ASK' else None,
            revision_request=None, verification_request='Confirm the input.' if kind == 'VERIFY_CONTEXT' else None))


def seed(repo, *, domain='food', located=True, count=3, sensitive=False):
    stamp = NOW.isoformat()
    loop = OpenLoop('loop_test', 'Test saved intention', domain, LoopStatus.ACTIVE, .8, stamp, stamp)
    repo.save_open_loop(loop)
    for i in range(count):
        metadata = {'latitude': '-37.8000', 'longitude': '144.9670', 'location_verified': 'true', 'location_source': 'explicit_test_fixture'} if located else {}
        if domain == 'shopping':
            metadata.update(location_role='store', store_name='Verified Zara branch fixture')
        entity = Entity(f'ent_{i}', 'product' if domain == 'shopping' else 'restaurant', domain, f'Test entity {i}', brand='Zara' if domain == 'shopping' else None, city='Melbourne', location_name='Carlton', metadata=metadata)
        evidence = Evidence(f'ev_{i}', 'offline_test_fixture', domain, 'Synthetic supporting evidence.', stamp, sensitive, 'high', f'IMG_TEST_{i}.PNG')
        repo.save_evidence(evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', .9)])
        repo.link_loop_entity(LoopEntity(loop.loop_id, entity.entity_id, 'subject', .9))
    return loop


def event(kind='LOCATION', id='ctx_test', **kw):
    data = dict(context_id=id, source='SIMULATED', type=kind, timestamp=NOW.isoformat(), timezone='Australia/Melbourne')
    if kind == 'LOCATION':
        data['location'] = dict(latitude=-37.8000, longitude=144.9670, accuracy_meters=20)
    if kind == 'CALENDAR':
        data.update(title='Lunch with Sarah', start_time=(NOW+timedelta(days=7)).isoformat(), end_time=(NOW+timedelta(days=7,hours=1)).isoformat(), location={'name': 'Carlton'})
    return ContextInput.model_validate({**data, **kw})


def request(*events, now=NOW):
    return EvaluationInput(now=now, events=list(events or [event()]))


class ContextNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = InMemoryLoopRepository()
        seed(self.repo)
        self.gateway = ScriptedGateway()
        self.clock = NOW
        self.service = ContextService(self.repo, gateway_factory=lambda: self.gateway, clock=lambda: self.clock)

    async def test_A_nearby_restaurants_real_workflow_receives_graph(self):
        result = await self.service.evaluate(request())
        self.assertEqual(result['result']['final_action'], 'SURFACE')
        self.assertEqual(result['delivery'], 'APPROVED_PENDING_DELIVERY')
        self.assertEqual(len(self.gateway.calls), 2)
        self.assertEqual(len(self.gateway.calls[0]['candidate_open_loops'][0]['entities']), 3)
        self.assertEqual(len(self.gateway.calls[1]['supporting_evidence']), 3)
        self.assertEqual(len(self.repo.notifications), 1)
        self.assertEqual(next(iter(self.repo.notifications.values())).payload['delivery_status'], 'APPROVED')
        self.assertTrue(all(t['receipt']['provider'] == 'nvidia' for t in result['result']['trace_events']))

    async def test_B_distant_location_no_model_or_notification(self):
        e = event(location={'latitude': 35.68, 'longitude': 139.69})
        result = await self.service.evaluate(request(e))
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse(self.repo.notifications)

    async def test_C_calendar_lunch_keeps_semantic_judgment_with_agents(self):
        result = await self.service.evaluate(request(event('CALENDAR')))
        self.assertEqual(result['result']['final_action'], 'SURFACE')
        ctx = self.gateway.calls[0]['context_events'][0]
        self.assertEqual(ctx['title'], 'Lunch with Sarah')
        self.assertEqual(ctx['metadata']['source'], 'SIMULATED')
        self.assertEqual(self.gateway.calls[0]['now'], NOW.isoformat())

    async def test_D_unrelated_appointment_respects_critic_silence(self):
        self.gateway.decisions = ['MATCH', 'STAY_SILENT']
        result = await self.service.evaluate(request(event('CALENDAR', title="Doctor's appointment")))
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
        self.assertEqual(len(self.gateway.calls), 2)
        self.assertFalse(self.repo.notifications)

    async def test_E_shopping_requires_verified_store_and_no_inventory_claim(self):
        repo = InMemoryLoopRepository(); seed(repo, domain='shopping', count=1)
        service = ContextService(repo, gateway_factory=lambda: self.gateway, clock=lambda: NOW)
        result = await service.evaluate(request())
        n = repo.get_notification(result['notification_id'])
        self.assertIsNotNone(n)
        self.assertNotIn('available', n.payload['message'])
        policy = self.gateway.calls[0]['context_events'][0]['metadata']['inventory_policy']
        self.assertIn('No product inventory', policy)
        self.assertIn('Verified Zara', json.dumps(result['candidates']))

    async def test_F_time_tick_includes_previously_stored_upcoming_trip(self):
        calendar = event('CALENDAR', 'ctx_trip', title='Tokyo trip', start_time=(NOW+timedelta(days=1)).isoformat(), end_time=(NOW+timedelta(days=5)).isoformat())
        self.repo.save_context_event(calendar.to_event())
        result = await self.service.evaluate(request(event('TIME')))
        self.assertEqual(result['result']['final_action'], 'SURFACE')
        events = self.gateway.calls[0]['context_events']
        self.assertEqual({e['context_id'] for e in events}, {'ctx_test', 'ctx_trip'})
        self.assertEqual(next(e for e in events if e['context_id']=='ctx_trip')['title'], 'Tokyo trip')

    async def test_G_replay_and_different_id_cooldown_do_not_call_models(self):
        first = await self.service.evaluate(request())
        replay = await self.service.evaluate(request())
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['notification_id'], replay['notification_id'])
        again = await self.service.evaluate(request(event(id='ctx_again')))
        self.assertEqual(again['result']['final_action'], 'STAY_SILENT')
        self.assertEqual(again['candidates'][0]['exclusion'], 'cooldown')
        self.assertEqual(len(self.gateway.calls), 2)
        self.assertEqual(len(self.repo.notifications), 1)

    async def test_H_resolved_loop_never_surfaces(self):
        self.repo.update_open_loop('loop_test', status=LoopStatus.RESOLVED)
        result = await self.service.evaluate(request())
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
        self.assertFalse(self.gateway.calls)

    async def test_same_context_cannot_notify_again_after_cooldown(self):
        await self.service.evaluate(request())
        self.clock += timedelta(days=2)
        later = await self.service.evaluate(request(now=NOW+timedelta(days=2)))
        self.assertEqual(later['result']['final_action'], 'STAY_SILENT')
        self.assertEqual(later['candidates'][0]['exclusion'], 'context_already_notified')
        self.assertEqual(len(self.gateway.calls), 2)

    async def test_I_suburb_without_coordinates_is_not_precise(self):
        repo = InMemoryLoopRepository(); seed(repo, located=False)
        result = await ContextService(repo, gateway_factory=lambda: self.gateway).evaluate(request())
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
        self.assertTrue(all(g['distance_meters'] is None for g in result['candidates'][0]['geography']))
        self.assertFalse(self.gateway.calls)

    async def test_J_context_failure_is_bounded_and_silent(self):
        self.gateway.decisions = [RuntimeError('secret-payload'), RuntimeError('secret-payload')]
        result = await self.service.evaluate(request())
        self.assertEqual(len(self.gateway.calls), 2)
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
        self.assertNotIn('secret-payload', json.dumps(result))
        self.assertFalse(self.repo.notifications)

    async def test_critic_failure_and_verification_remain_silent(self):
        for replies in [('MATCH', RuntimeError('private'), RuntimeError('private')), ('MATCH', 'VERIFY_CONTEXT')]:
            self.gateway.decisions = list(replies)
            self.repo.context_evaluations.clear()
            result = await self.service.evaluate(request())
            self.assertEqual(result['result']['final_action'], 'STAY_SILENT')
            self.assertFalse(self.repo.notifications)

    async def test_missing_receipt_blocks_delivery_without_rewriting_agent_result(self):
        self.gateway.receipts = False
        result = await self.service.evaluate(request())
        self.assertEqual(result['result']['final_action'], 'SURFACE')
        self.assertEqual(result['delivery'], 'BLOCKED_UNVERIFIED_MODEL_RECEIPT')
        self.assertFalse(self.repo.notifications)

    async def test_ask_is_reported_without_inventing_merge_feedback(self):
        self.gateway.decisions = ['MATCH', 'ASK']
        result = await self.service.evaluate(request())
        self.assertEqual(result['result']['final_action'], 'ASK')
        self.assertTrue(result['result']['question'])
        self.assertFalse(self.repo.notifications)
        self.assertFalse(self.repo.check_ins)

    async def test_sensitive_chain_never_enters_models_or_results(self):
        self.repo.evidence['ev_0'] = replace(self.repo.evidence['ev_0'], sensitive=True, summary='PRIVATE_SCREENSHOT')
        result = await self.service.evaluate(request())
        self.assertFalse(self.gateway.calls)
        self.assertNotIn('PRIVATE_SCREENSHOT', json.dumps(result))
        self.assertFalse(result['candidates'])

    async def test_gps_accuracy_conservatively_excludes_large_radius(self):
        result = await self.service.evaluate(request(event(location={'latitude': -37.8, 'longitude': 144.967, 'accuracy_meters': 2000})))
        self.assertFalse(self.gateway.calls)
        self.assertEqual(result['result']['final_action'], 'STAY_SILENT')

    async def test_context_id_conflicts_do_not_overwrite(self):
        await self.service.evaluate(request())
        with self.assertRaises(ContextConflict):
            await self.service.evaluate(request(event(title='different')))
        self.assertEqual(self.repo.get_context_events()[0].title, 'Location')

    async def test_delivery_read_and_done_are_persisted_separately(self):
        result = await self.service.evaluate(request())
        nid = result['notification_id']
        await self.service.action(nid, 'DELIVERED')
        await self.service.action(nid, 'DELIVERED')
        await self.service.action(nid, 'READ')
        await self.service.action(nid, 'DONE')
        n = self.repo.get_notification(nid)
        self.assertEqual([e['action'] for e in n.payload['feedback_events']], ['DELIVERED', 'READ', 'DONE'])
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.RESOLVED)
        self.assertEqual(self.service.list_notifications(), [])
        self.assertEqual(len(self.repo.evidence), 3)

    async def test_snooze_and_terminal_feedback_apply_to_loop(self):
        result = await self.service.evaluate(request())
        nid = result['notification_id']
        await self.service.action(nid, 'READ')
        await self.service.action(nid, 'SNOOZE')
        self.assertEqual(self.service.list_notifications(), [])
        self.clock += timedelta(hours=25)
        self.assertEqual(len(self.service.list_notifications()), 1)
        self.assertFalse(self.service.list_notifications()[0]['payload']['read'])
        self.assertEqual(self.service.list_notifications()[0]['payload']['delivery_status'], 'APPROVED')
        await self.service.action(nid, 'JUST_INSPIRATION')
        self.assertEqual(self.repo.get_open_loop('loop_test').status, LoopStatus.ACTIVE)
        self.assertEqual(self.service._blocked('loop_test'), 'user_feedback')
        with self.assertRaises(ContextConflict):
            await self.service.action(nid, 'DONE')

    async def test_read_only_poll_does_not_reason(self):
        await self.service.evaluate(request())
        for _ in range(5):
            self.service.list_notifications()
        self.assertEqual(len(self.gateway.calls), 2)

    async def test_persistent_sql_store_survives_service_restart(self):
        sql = SqlHarness(); self.addCleanup(sql.db.close)
        sql.db.executescript('CREATE TABLE context_evaluations (evaluation_id TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT); CREATE TABLE notifications (notification_id TEXT PRIMARY KEY, loop_id TEXT, created_at TEXT, payload_json TEXT);')
        repo = ZetarisRepository(sql); seed(repo)
        first = ContextService(repo, gateway_factory=lambda: self.gateway, clock=lambda: NOW)
        result = await first.evaluate(request())
        second = ContextService(repo, gateway_factory=lambda: (_ for _ in ()).throw(AssertionError('No new models')), clock=lambda: NOW)
        replay = await second.evaluate(request())
        self.assertTrue(replay['replayed'])
        self.assertEqual(second.list_notifications()[0]['notification_id'], result['notification_id'])
        await second.action(result['notification_id'], 'NOT_RELEVANT')
        self.assertEqual(second.list_notifications(), [])
        self.assertEqual(repo.get_notification(result['notification_id']).payload['feedback'], 'NOT_RELEVANT')

    async def test_sql_failed_notification_write_does_not_publish_approval(self):
        sql = SqlHarness(); self.addCleanup(sql.db.close)
        sql.db.executescript('CREATE TABLE context_evaluations (evaluation_id TEXT PRIMARY KEY, created_at TEXT, payload_json TEXT); CREATE TABLE notifications (notification_id TEXT PRIMARY KEY, loop_id TEXT, created_at TEXT, payload_json TEXT);')
        repo = ZetarisRepository(sql); seed(repo)
        sql.failures.append(lambda q: q.startswith('MERGE INTO recall_data.app.notifications'))
        result = await ContextService(repo, gateway_factory=lambda: self.gateway, clock=lambda: NOW).evaluate(request())
        self.assertEqual(result['state'], 'FAILED_SAFE')
        self.assertFalse(repo.list_notifications())
        self.assertEqual(repo.get_context_evaluation(request().fingerprint()).payload['state'], 'FAILED_SAFE')


class ContextInputTests(unittest.TestCase):
    def test_aware_time_and_coordinates_required(self):
        with self.assertRaises(ValidationError):
            event(timestamp='2026-10-26T12:30:00')
        for location in ({'latitude': 91, 'longitude': 0}, {'latitude': 0}, {'latitude': float('nan'), 'longitude': 0}):
            with self.assertRaises(ValidationError):
                event(location=location)
        with self.assertRaises(ValidationError):
            event('CALENDAR', end_time=NOW.isoformat())
        with self.assertRaises(ValidationError):
            request(event(), event(id='ctx_live', source='BROWSER'))

    def test_haversine_and_reserved_source(self):
        self.assertEqual(distance_meters(-37.8,144.967,-37.8,144.967), 0)
        self.assertGreater(distance_meters(-37.8,144.967,35.68,139.69), 1000000)
        self.assertEqual(event(metadata={'source':'BROWSER'}).to_event().metadata['source'], 'SIMULATED')

    def test_sample_http_rejects_real_agent_claim_and_poll_never_calls_models(self):
        with patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True), TestClient(app) as client:
            response = client.post('/context-simulator/evaluate', json=request().model_dump(mode='json'))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(client.get('/notifications').json(), [])
            self.assertEqual(client.get('/notifications/missing').status_code, 404)
            self.assertEqual(client.post('/notifications/missing/actions', json={'action':'BUY_NOW'}).status_code, 422)
