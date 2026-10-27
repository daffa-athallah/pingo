"""Offline end-to-end clarification fixtures; no live model/database claims."""
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.agents.open_loop import OpenLoopAgent
from backend.app.checkin_clarifications import (after_upload, after_critic, available, queue, grounding,
    ClarificationService, ClarificationConflict, KIND)
from backend.app.context.service import ContextService
from backend.app.domain.models import LoopStatus
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.tests.test_context_notifications import NOW, MODEL, seed, ScriptedGateway, request
from backend.tests.test_notification_feedback import FeedbackGateway
from backend.tests.test_upload_api import Base, FakeGateway, PNG, PNG2


QUESTION = {'question': 'What did you have in mind for this saved place?', 'options': [
    {'value': 'option_1', 'label': 'Thinking of visiting'}, {'value': 'option_2', 'label': 'Just inspiration'}]}


def decision(kind='CREATE', loop=None):
    return {'decision': kind, 'target_loop_id': loop, 'proposed_title': 'Interested in a saved restaurant' if kind in {'CREATE', 'REVISE'} else None,
        'domain': 'food', 'confidence': .8, 'concise_reason': 'Explicit offline clarification fixture.',
        'supporting_evidence_ids': ['ev_0'], 'supporting_entity_ids': ['ent_0'], 'material_uncertainty': None}


class ClarificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = patch.dict('os.environ', {'SAMPLE_MODE': 'false'})
        p.start(); self.addCleanup(p.stop)
        self.repo = InMemoryLoopRepository(); seed(self.repo)
        self.evidence, self.entities = grounding(self.repo, ['ev_0'], ['ent_0'])

    def queued(self, *, loop='loop_test', stamp=NOW):
        qid = queue(self.repo, self.evidence, self.entities, text=QUESTION['question'], options=QUESTION['options'],
            uncertainty='Visit or inspiration?', origin='OPEN_LOOP', loop_id=loop, clock=lambda: stamp)
        return self.repo.get_check_in(qid)

    def service(self, *replies, **kw):
        self.gateway = FeedbackGateway(*replies, **kw)
        return ClarificationService(self.repo, lambda: self.gateway, clock=lambda: NOW)

    async def test_uncertain_upload_generates_grounded_question(self):
        gateway = FeedbackGateway(QUESTION)
        agent = OpenLoopAgent(gateway, self.repo)
        emitted = []
        qid = await after_upload(agent, self.repo, SimpleNamespace(material_uncertainty='Visit or inspiration?'),
            SimpleNamespace(evidence_id='ev_0', loop_id='loop_test'), lambda *args, **kw: emitted.append((args, kw)))
        self.assertIsNotNone(qid)
        q = self.repo.get_check_in(qid)
        self.assertEqual(q.kind, KIND)
        self.assertEqual(q.question['response_mode'], 'options')
        self.assertEqual(q.question['_evidence_ids'], ['ev_0'])
        self.assertEqual([e[0][1] for e in emitted[-2:]], ['ASK', 'QUEUED'])
        self.assertEqual(len(gateway.calls), 1)

    async def test_scenery_with_only_a_city_asks_without_a_named_place(self):
        from backend.app.domain.models import Evidence
        scene = Evidence('ev_scene', 'upload', 'travel', 'A mountain valley at sunrise; the caption only says Queenstown.', NOW.isoformat(), False, 'high', 'scene.png')
        self.repo.save_evidence(scene, [], [])
        gateway = FeedbackGateway(QUESTION)
        emitted = []
        qid = await after_upload(OpenLoopAgent(gateway, self.repo), self.repo, SimpleNamespace(material_uncertainty=None),
            SimpleNamespace(evidence_id='ev_scene', loop_id=None), lambda *a, **k: emitted.append(a))
        self.assertIsNotNone(qid)
        self.assertEqual(self.repo.get_check_in(qid).question['_entity_ids'], [])
        self.assertEqual(self.repo.get_check_in(qid).question['_key'], ['ev_scene'])
        self.assertEqual([e[1] for e in emitted[-2:]], ['ASK', 'QUEUED'])

    async def test_confident_upload_does_not_call_model(self):
        gateway = FeedbackGateway()
        result = await after_upload(OpenLoopAgent(gateway, self.repo), self.repo, SimpleNamespace(material_uncertainty=None),
            SimpleNamespace(evidence_id='ev_0', loop_id='loop_test'), lambda *a, **k: None)
        self.assertIsNone(result); self.assertEqual(gateway.calls, [])

    async def test_repeated_uncertainty_does_not_repeat_question_or_model(self):
        gateway = FeedbackGateway(QUESTION)
        args = (OpenLoopAgent(gateway, self.repo), self.repo, SimpleNamespace(material_uncertainty='Visit or inspiration?'),
            SimpleNamespace(evidence_id='ev_0', loop_id='loop_test'), lambda *a, **k: None)
        self.assertIsNotNone(await after_upload(*args))
        self.assertIsNone(await after_upload(*args))
        self.assertEqual(len(gateway.calls), 1)

    async def test_sensitive_uncertainty_never_sent(self):
        self.repo.evidence['ev_0'] = replace(self.evidence[0], sensitive=True)
        gateway = FeedbackGateway()
        self.assertIsNone(await after_upload(OpenLoopAgent(gateway, self.repo), self.repo,
            SimpleNamespace(material_uncertainty='Private detail'), SimpleNamespace(evidence_id='ev_0', loop_id=None), lambda *a, **k: None))
        self.assertEqual(gateway.calls, [])

    async def test_bad_generation_retries_without_fake_question(self):
        gateway = FeedbackGateway({'question': 'bad'}, {'question': 'bad'})
        self.assertIsNone(await after_upload(OpenLoopAgent(gateway, self.repo), self.repo,
            SimpleNamespace(material_uncertainty='Unclear'), SimpleNamespace(evidence_id='ev_0', loop_id=None), lambda *a, **k: None))
        self.assertEqual(len(gateway.calls), 2); self.assertEqual(self.repo.get_check_ins(), [])

    async def test_critic_ask_persists_and_replays_without_notification(self):
        gateway = ScriptedGateway(('MATCH', 'ASK'))
        service = ContextService(self.repo, gateway_factory=lambda: gateway, clock=lambda: NOW)
        result = await service.evaluate(request())
        self.assertIsNotNone(result['check_in_id'])
        item = self.repo.get_check_in(result['check_in_id'])
        self.assertEqual(item.question['_origin'], 'CRITIC')
        self.assertEqual(result['notification_id'], None)
        self.assertEqual(self.repo.list_notifications(), [])
        self.assertEqual((await service.evaluate(request()))['check_in_id'], result['check_in_id'])
        self.assertEqual(len(self.repo.get_check_ins()), 1)
        from backend.tests.test_context_notifications import event
        next_result = await service.evaluate(request(event(id='ctx_after_question')))
        self.assertEqual(next_result['result']['final_action'], 'STAY_SILENT')
        self.assertTrue(any(candidate['exclusion'] == 'awaiting_clarification' for candidate in next_result['candidates']))
        self.assertEqual(len(gateway.calls), 2)

    async def test_answer_reaches_open_loop_and_updates_only_target(self):
        item = self.queued()
        before = dict(self.repo.evidence)
        result = await self.service(decision('REVISE', 'loop_test')).respond(item.check_in_id, 'option_1', None)
        self.assertEqual(result['agent_review']['state'], 'COMPLETED')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Interested in a saved restaurant')
        self.assertEqual(self.gateway.calls[0]['clarification']['answer'], 'Thinking of visiting')
        self.assertEqual(self.repo.evidence, before)
        self.assertEqual(len(self.repo.loops), 1)

    async def test_unresolved_without_loop_can_create_after_answer(self):
        self.repo.loops.clear(); self.repo.loop_entities.clear()
        item = self.queued(loop=None)
        result = await self.service(decision()).respond(item.check_in_id, 'option_1', None)
        self.assertEqual(result['agent_review']['state'], 'COMPLETED')
        self.assertEqual(len(self.repo.loops), 1)
        self.assertTrue(self.repo.get_loop_entities([result['agent_review']['loop_id']]))

    async def test_newer_loop_is_offered_instead_of_duplicated(self):
        item = self.queued(loop=None)
        result = await self.service(decision('CREATE'), decision('CREATE')).respond(item.check_in_id, 'option_1', None)
        self.assertEqual(result['agent_review']['state'], 'FAILED_SAFE')
        self.assertEqual(len(self.repo.loops), 1)

    async def test_answer_persists_on_failure_and_duplicate_does_not_bill_again(self):
        item = self.queued()
        service = self.service(OSError('private'), OSError('private'))
        result = await service.respond(item.check_in_id, 'option_1', None)
        self.assertEqual(result['agent_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_check_in(item.check_in_id).response, 'option_1')
        self.assertEqual(await service.respond(item.check_in_id, 'option_1', None), result)
        self.assertEqual(len(self.gateway.calls), 2)
        with self.assertRaises(ClarificationConflict):
            await service.respond(item.check_in_id, 'option_2', None)

    async def test_other_requires_actual_text_and_unsupported_value_rejected(self):
        item = self.queued(); service = self.service()
        for value, comment in [('yes', None), ('other', None), ('option_1', 'unsolicited')]:
            with self.assertRaises(ValueError): await service.respond(item.check_in_id, value, comment)
        self.assertEqual(self.repo.get_check_in(item.check_in_id).status, 'PENDING')
        self.assertEqual(self.gateway.calls, [])

    async def test_not_sure_defers_without_model_and_cooldown(self):
        item = self.queued(); service = self.service()
        result = await service.respond(item.check_in_id, 'not_sure', None)
        self.assertEqual(result['agent_review']['state'], 'DEFERRED')
        self.assertEqual(self.gateway.calls, [])
        self.assertFalse(available(self.repo, ['ent_0'], NOW))
        self.assertTrue(available(self.repo, ['ent_0'], NOW + timedelta(hours=25)))
        from backend.tests.test_context_notifications import event
        eligible, diagnostics = ContextService(self.repo, clock=lambda: NOW).candidates([event().to_event()])
        self.assertEqual(eligible, [])
        self.assertEqual(diagnostics[0]['exclusion'], 'awaiting_clarification')

    async def test_question_budget_three_pending(self):
        for index in range(3):
            evidence, entities = grounding(self.repo, [f'ev_{index}'], [f'ent_{index}'])
            self.assertIsNotNone(queue(self.repo, evidence, entities, text='Question?', options=QUESTION['options'],
                uncertainty='Unclear', origin='OPEN_LOOP', clock=lambda: NOW))
        self.assertFalse(available(self.repo, ['ent_new'], NOW))

    async def test_unverified_receipt_cannot_mutate_loop(self):
        item = self.queued()
        result = await self.service(decision('REVISE', 'loop_test'), decision('REVISE', 'loop_test'), receipt=False).respond(item.check_in_id, 'option_1', None)
        self.assertEqual(result['agent_review']['state'], 'FAILED_SAFE')
        self.assertEqual(self.repo.get_open_loop('loop_test').title, 'Test saved intention')

    async def test_other_answer_text_is_forwarded_without_fabrication(self):
        item = self.queued()
        await self.service(decision('REVISE', 'loop_test')).respond(item.check_in_id, 'other', 'Just collecting ideas for a friend')
        self.assertEqual(self.gateway.calls[0]['clarification']['comment'], 'Just collecting ideas for a friend')

    async def test_unverified_question_receipt_does_not_publish(self):
        gateway = FeedbackGateway(QUESTION, QUESTION, receipt=False)
        self.assertIsNone(await after_upload(OpenLoopAgent(gateway, self.repo), self.repo,
            SimpleNamespace(material_uncertainty='Unclear'), SimpleNamespace(evidence_id='ev_0', loop_id=None), lambda *a, **k: None))
        self.assertEqual(self.repo.get_check_ins(), [])


class UploadClarificationGateway(FakeGateway):
    reasoning_model = MODEL

    async def complete(self, messages, **kw):
        content = messages[-1]['content']
        if isinstance(content, str):
            payload = json.loads(content)
            if 'uncertainty' in payload:
                self.last_routing = {'requested_model': MODEL, 'routed_model': MODEL, 'provider': 'nvidia'}
                self.calls.append('clarification')
                return json.dumps(QUESTION)
        raw = json.loads(await super().complete(messages, **kw))
        if isinstance(content, str):
            raw.update(decision='LEAVE_UNRESOLVED', proposed_title=None, target_loop_id=None, material_uncertainty='Visit or inspiration?')
        return json.dumps(raw)


class UploadCheckInTests(Base):
    def test_http_answer_reaches_agent_and_persists_real_repository_loop(self):
        self.gateway = UploadClarificationGateway()
        qid = self.post().json()['outcome']['check_in_id']
        gateway = FeedbackGateway()
        async def complete(messages, **kw):
            payload = json.loads(messages[-1]['content'])
            gateway.calls.append(payload)
            gateway.last_routing = {'requested_model': MODEL, 'routed_model': MODEL, 'provider': 'nvidia'}
            result = decision()
            result.update(supporting_evidence_ids=[e['evidence_id'] for e in payload['supporting_evidence']],
                          supporting_entity_ids=[e['entity_id'] for e in payload['entities']])
            return json.dumps(result)
        gateway.complete = complete
        @asynccontextmanager
        async def factory():
            yield gateway
        with patch('backend.app.context_api._gateway', factory):
            response = self.client.post(f'/api/check-ins/{qid}/respond', json={'response': 'option_1'})
        self.assertEqual(response.status_code, 200)
        result = response.json()['agent_review']
        self.assertEqual(result['state'], 'COMPLETED')
        self.assertIsNotNone(self.repo.get_open_loop(result['loop_id']))
        self.assertEqual(len(self.repo.list_evidence()), 1)
        self.assertEqual(self.client.get('/api/check-ins').json()['questions'], [])

    def test_real_upload_to_checkin_get_and_answer_routes(self):
        self.gateway = UploadClarificationGateway()
        uploaded = self.post().json()
        qid = uploaded['outcome']['check_in_id']
        self.assertIsNotNone(qid)
        item = self.repo.get_check_in(qid)
        self.assertEqual(item.loop_id, '')  # No fabricated intention while uncertain.
        response = self.client.get('/api/check-ins')
        self.assertEqual(response.status_code, 200)
        question = response.json()['questions'][0]
        self.assertEqual(question['id'], qid)
        self.assertFalse(any(key.startswith('_') for key in question))
        self.assertEqual(len(question['supporting_images']), 1)
        self.assertEqual(self.client.post(f'/api/check-ins/{qid}/respond', json={'response': 'other'}).status_code, 422)
        result = self.client.post(f'/api/check-ins/{qid}/respond', json={'response': 'not_sure'}).json()
        self.assertEqual(result['agent_review']['state'], 'DEFERRED')
        self.assertEqual(self.client.get('/api/check-ins').json()['questions'], [])

    def test_unanswered_clarifications_survive_day_change(self):
        self.gateway = UploadClarificationGateway()
        qid = self.post().json()['outcome']['check_in_id']
        with patch('backend.app.main._today', return_value='2099-01-01'):
            self.assertEqual(self.client.get('/api/check-ins').json()['questions'][0]['id'], qid)

    def test_repeat_photo_does_not_ask_twice(self):
        self.gateway = UploadClarificationGateway()
        self.post()
        self.post(PNG2)
        self.assertEqual(len(self.repo.get_check_ins()), 1)
        self.assertEqual(self.gateway.calls.count('clarification'), 1)
