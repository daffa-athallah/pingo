"""Offline orchestrator checks: real agents driven by scripted gateways, no network."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.agents.context import ContextAgent
from backend.app.agents.critic import CriticAgent
from backend.app.agents.evidence import Entity, Evidence, EvidenceAgent, Location
from backend.app.agents.open_loop import OpenLoopAgent
from backend.app.domain.models import ContextEvent, ContextType, LoopEntity, LoopStatus, OpenLoop
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.orchestration.recall import (FinalAction, RecallOrchestrator, RunType, VerificationResult)
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.tests.test_context import NONE, reply as context_reply
from backend.tests.test_critic import SILENT, reply as critic_base
from backend.tests.test_open_loop import FakeGateway

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 16
DINNER = ContextEvent('ctx_cal', ContextType.CALENDAR, 'Dinner with Alex', '2026-10-25T19:00:00+00:00', 'Carlton', 'Melbourne')
VERIFIED = ContextEvent('ctx_cal', ContextType.CALENDAR, 'Dinner with Alex (confirmed)', '2026-10-25T19:00:00+00:00', 'Carlton', 'Melbourne')


class Script(FakeGateway):
    """Replies may be strings, callables(messages) or Exceptions to raise."""
    def __init__(self, *replies, vision_model=None):
        super().__init__(*replies)
        self.vision_model = vision_model

    async def complete(self, messages, *, max_tokens=2048, model=None):
        self.calls.append({'messages': messages, 'model': model})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply(messages) if callable(reply) else reply


class FakeVerifier:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def verify(self, request, events):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result


def extraction_json(**kw):
    base = {'domain': 'food', 'summary': 'Saved Carlton restaurants.', 'sensitive': False, 'confidence': 'high',
            'entities': [{'name': 'Brunetti', 'type': 'restaurant', 'location': {'location_name': 'Carlton', 'city': 'Melbourne', 'country': None}}]}
    return json.dumps({**base, **kw})


def open_loop_reply(decision='CREATE', **kw):
    def build(messages):
        sent = json.loads(messages[1]['content'])
        base = {'decision': decision, 'target_loop_id': None, 'proposed_title': 'Interested in Brunetti in Carlton',
                'domain': 'food', 'confidence': 0.6, 'concise_reason': 'Saved a venue.',
                'supporting_evidence_ids': [sent['new_evidence']['evidence_id']],
                'supporting_entity_ids': [e['entity_id'] for e in sent['new_entities']], 'material_uncertainty': None}
        return json.dumps({**base, **kw})
    return build


def critic_reply(**kw):
    return critic_base(**{'supporting_evidence_ids': ['ev_1'], **kw})


REVISION_CRITIC = dict(decision='REQUEST_REVISION', revision_request='Title promises a time the evidence does not show.',
                       supporting_context_ids=[], concise_reason='Timing exceeds the evidence.')
VERIFY_CRITIC = dict(decision='VERIFY_CONTEXT', verification_request='Confirm the dinner location.',
                     supporting_context_ids=['ctx_cal'], concise_reason='Location needs confirming.')


def seed(repo, title='Eat at Brunetti tomorrow night'):
    extraction = Evidence('food', 'Saved Carlton restaurants.', [
        Entity('Brunetti', 'restaurant', location=Location('Carlton', 'Melbourne', None))], False, 'high')
    result = ingest(extraction, repo, new_id=lambda: 'ev_1', captured_at='2026-10-20T10:00:00+00:00')
    repo.save_open_loop(OpenLoop('loop_carlton', title, 'food', LoopStatus.OPEN, 0.7, 'a', '2026-10-24T10:00:00+00:00'))
    for entity in result.entities:
        repo.link_loop_entity(LoopEntity('loop_carlton', entity.entity_id, 'subject', 0.7))
    return result


class Harness:
    def __init__(self, *, vision=(), open_loop=(), context=(), critic=(), verifier=None, repo=None):
        self.repo = repo or InMemoryLoopRepository()
        self.vg, self.og = Script(*vision, vision_model='vision-test'), Script(*open_loop)
        self.cg, self.kg = Script(*context), Script(*critic)
        self.verifier = verifier
        ids = iter(f'run_{i}' for i in range(10))
        self.orch = RecallOrchestrator(EvidenceAgent(self.vg), OpenLoopAgent(self.og, self.repo, new_id=lambda: 'loop_new'),
                                       ContextAgent(self.cg, self.repo), CriticAgent(self.kg, self.repo), self.repo,
                                       verifier, now=lambda: '2026-10-25T12:00:00+00:00', new_run_id=lambda: next(ids))


def agents(result):
    return [e.agent for e in result.trace_events]


def actions(result):
    return [e.action for e in result.trace_events]


class ScreenshotFlowTests(unittest.IsolatedAsyncioTestCase):
    def image(self, tmp):
        path = Path(tmp) / 'shot.png'
        path.write_bytes(PNG)
        return path

    async def test_new_screenshot_stores_and_never_runs_context_or_critic(self):
        h = Harness(vision=[extraction_json()], open_loop=[open_loop_reply()])
        with tempfile.TemporaryDirectory() as tmp:
            result = await h.orch.ingest_screenshot(self.image(tmp))
        self.assertEqual((result.final_action, result.run_type, result.loop_id), (FinalAction.STORED, RunType.EVIDENCE_INGESTION, 'loop_new'))
        self.assertEqual((h.cg.calls, h.kg.calls), ([], []))
        self.assertEqual(agents(result), ['EVIDENCE', 'INGESTION', 'OPEN_LOOP'])
        self.assertEqual([e.next_step for e in result.trace_events], ['INGESTION', 'OPEN_LOOP', 'STOP'])
        self.assertEqual(len(h.repo.evidence), 1)
        self.assertIn(result.evidence_id, h.repo.evidence)
        self.assertEqual(h.repo.loops['loop_new'].status, LoopStatus.OPEN)

    async def test_sensitive_screenshot_is_stored_but_never_reasoned_over(self):
        h = Harness(vision=[extraction_json(sensitive=True)])
        with tempfile.TemporaryDirectory() as tmp:
            result = await h.orch.ingest_screenshot(self.image(tmp))
        self.assertEqual((result.final_action, result.loop_id, h.og.calls), (FinalAction.STORED, None, []))
        self.assertEqual(actions(result), ['EXTRACT', 'STORE', 'IGNORE'])

    async def test_evidence_failure_persists_nothing_after_one_retry(self):
        h = Harness(vision=['not json', 'still not json'], open_loop=[open_loop_reply()])
        with tempfile.TemporaryDirectory() as tmp:
            result = await h.orch.ingest_screenshot(self.image(tmp))
        self.assertEqual(result.final_action, FinalAction.FAILED_SAFE)
        self.assertEqual((len(h.vg.calls), h.og.calls), (2, []))
        self.assertEqual((h.repo.evidence, h.repo.entities, h.repo.evidence_entities, h.repo.loops), ({}, {}, [], {}))
        self.assertEqual(actions(result), ['RETRY', 'FAILED'])

    async def test_open_loop_failure_keeps_evidence_but_invents_no_loop(self):
        h = Harness(vision=[extraction_json()], open_loop=['bad', 'bad'])
        with tempfile.TemporaryDirectory() as tmp:
            result = await h.orch.ingest_screenshot(self.image(tmp))
        self.assertEqual((result.final_action, result.loop_id), (FinalAction.FAILED_SAFE, None))
        self.assertIn(result.evidence_id, h.repo.evidence)
        self.assertEqual((h.repo.loops, h.repo.loop_entities, len(h.og.calls)), ({}, [], 2))

    async def test_a_single_retry_can_recover(self):
        h = Harness(vision=[RuntimeError('boom'), extraction_json()], open_loop=[open_loop_reply()])
        with tempfile.TemporaryDirectory() as tmp:
            result = await h.orch.ingest_screenshot(self.image(tmp))
        self.assertEqual(result.final_action, FinalAction.STORED)
        self.assertEqual(actions(result), ['RETRY', 'EXTRACT', 'STORE', 'CREATE'])
        self.assertNotIn('boom', json.dumps(result.to_dict()))  # unexpected errors are reduced to a class name


class ContextFlowTests(unittest.IsolatedAsyncioTestCase):
    def harness(self, **kw):
        h = Harness(**kw)
        seed(h.repo)
        return h

    async def test_match_then_critic_surfaces(self):
        h = self.harness(context=[context_reply()], critic=[critic_reply()])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, result.loop_id, result.run_type), (FinalAction.SURFACE, 'loop_carlton', RunType.CONTEXT_EVALUATION))
        self.assertEqual(result.message_payload['title'], 'Eat at Brunetti tomorrow night')
        self.assertEqual(agents(result), ['CONTEXT', 'CRITIC'])
        self.assertEqual([e.next_step for e in result.trace_events], ['CRITIC', 'OUTPUT'])
        self.assertEqual((len(h.cg.calls), len(h.kg.calls), h.og.calls), (1, 1, []))

    async def test_critic_can_stay_silent(self):
        h = self.harness(context=[context_reply()], critic=[critic_reply(decision='STAY_SILENT', **{**SILENT, 'supporting_evidence_ids': []})])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, result.message_payload), (FinalAction.STAY_SILENT, None))
        self.assertEqual(result.trace_events[-1].next_step, 'STOP')

    async def test_critic_ask_returns_the_question(self):
        h = self.harness(context=[context_reply()], critic=[critic_reply(
            decision='ASK', question='Is this for a special occasion?', material_uncertainty='Occasion unknown',
            supporting_context_ids=[])])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, result.question), (FinalAction.ASK, 'Is this for a special occasion?'))
        self.assertEqual(result.trace_events[-1].next_step, 'CHECK_IN')

    async def test_context_no_match_never_calls_critic(self):
        h = self.harness(context=[context_reply(**NONE)])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, h.kg.calls, agents(result)), (FinalAction.STAY_SILENT, [], ['CONTEXT']))

    async def test_no_active_loops_means_no_model_call_at_all(self):
        h = Harness()
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, h.cg.calls, h.kg.calls), (FinalAction.STAY_SILENT, [], []))

    async def test_critic_failure_twice_never_surfaces(self):
        h = self.harness(context=[context_reply()], critic=['bad', critic_reply(supporting_evidence_ids=['ev_invented'])])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, len(h.kg.calls)), (FinalAction.STAY_SILENT, 2))
        self.assertEqual(actions(result), ['MATCH', 'RETRY', 'FAILED'])

    async def test_critic_exception_never_surfaces(self):
        h = self.harness(context=[context_reply()], critic=[RuntimeError('x'), RuntimeError('y')])
        self.assertEqual((await h.orch.evaluate_context([DINNER])).final_action, FinalAction.STAY_SILENT)

    async def test_context_failure_twice_never_surfaces_and_skips_critic(self):
        h = self.harness(context=['bad', 'bad'], critic=[critic_reply()])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, h.kg.calls, len(h.cg.calls)), (FinalAction.STAY_SILENT, [], 2))

    async def test_critic_retry_can_recover(self):
        h = self.harness(context=[context_reply()], critic=['bad', critic_reply()])
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, actions(result)), (FinalAction.SURFACE, ['MATCH', 'RETRY', 'SURFACE']))


class RevisionBranchTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_revision_really_calls_open_loop_and_critic_again(self):
        h = Harness(context=[context_reply()], critic=[critic_reply(**REVISION_CRITIC), critic_reply()],
                    open_loop=[open_loop_reply('REVISE', target_loop_id='loop_carlton',
                                               proposed_title='Interested in trying Brunetti in Carlton',
                                               concise_reason='Removed the unsupported timing.')])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual(result.final_action, FinalAction.SURFACE)
        self.assertEqual((len(h.og.calls), len(h.kg.calls), len(h.cg.calls)), (1, 2, 1))
        self.assertEqual(h.repo.loops['loop_carlton'].title, 'Interested in trying Brunetti in Carlton')
        self.assertEqual(result.message_payload['title'], 'Interested in trying Brunetti in Carlton')
        self.assertEqual(agents(result), ['CONTEXT', 'CRITIC', 'OPEN_LOOP', 'CRITIC'])
        self.assertEqual(actions(result), ['MATCH', 'REQUEST_REVISION', 'REVISE', 'SURFACE'])
        self.assertEqual([e.next_step for e in result.trace_events], ['CRITIC', 'OPEN_LOOP', 'CRITIC', 'OUTPUT'])
        self.assertEqual((result.revision_count, result.verification_count), (1, 0))
        sent = json.loads(h.og.calls[0]['messages'][1]['content'])
        self.assertEqual(sent['revision_request']['target_loop_id'], 'loop_carlton')
        self.assertIn('evidence does not show', sent['revision_request']['request'])
        # the second Critic call saw the revised title, and evidence was never touched
        self.assertIn('Interested in trying Brunetti', h.kg.calls[1]['messages'][1]['content'])
        self.assertEqual(list(h.repo.evidence), ['ev_1'])

    async def test_second_revision_request_stops_safely_without_looping(self):
        h = Harness(context=[context_reply()], critic=[critic_reply(**REVISION_CRITIC), critic_reply(**REVISION_CRITIC), critic_reply()],
                    open_loop=[open_loop_reply('REVISE', target_loop_id='loop_carlton', proposed_title='Interested in Brunetti')])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual(result.final_action, FinalAction.STAY_SILENT)
        self.assertEqual((len(h.og.calls), len(h.kg.calls), result.revision_count), (1, 2, 1))
        self.assertEqual(result.trace_events[-1].next_step, 'STOP')
        self.assertEqual(len(h.kg.replies), 1)  # the third scripted Critic reply was never consumed

    async def test_open_loop_that_declines_to_revise_ends_silent_without_second_critic(self):
        h = Harness(context=[context_reply()], critic=[critic_reply(**REVISION_CRITIC), critic_reply()],
                    open_loop=[open_loop_reply('LEAVE_UNRESOLVED', proposed_title=None, material_uncertainty='Unclear plan.')])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, len(h.kg.calls), len(h.og.calls)), (FinalAction.STAY_SILENT, 1, 1))
        self.assertEqual(h.repo.loops['loop_carlton'].title, 'Eat at Brunetti tomorrow night')

    async def test_revision_cannot_create_a_duplicate_loop(self):
        h = Harness(context=[context_reply()], critic=[critic_reply(**REVISION_CRITIC)],
                    open_loop=[open_loop_reply('CREATE'), open_loop_reply('CREATE')])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual(result.final_action, FinalAction.STAY_SILENT)
        self.assertEqual(list(h.repo.loops), ['loop_carlton'])


class VerificationBranchTests(unittest.IsolatedAsyncioTestCase):
    async def test_critic_verify_context_calls_verifier_then_context_and_critic_again(self):
        verifier = FakeVerifier(VerificationResult(True, [VERIFIED], 'Calendar confirmed.'))
        h = Harness(context=[context_reply(), context_reply()], critic=[critic_reply(**VERIFY_CRITIC), critic_reply()], verifier=verifier)
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual(result.final_action, FinalAction.SURFACE)
        self.assertEqual((len(verifier.calls), len(h.cg.calls), len(h.kg.calls)), (1, 2, 2))
        self.assertEqual(verifier.calls[0].request, 'Confirm the dinner location.')
        self.assertEqual(agents(result), ['CONTEXT', 'CRITIC', 'VERIFIER', 'CONTEXT', 'CRITIC'])
        self.assertEqual(actions(result), ['MATCH', 'VERIFY_CONTEXT', 'VERIFIED', 'MATCH', 'SURFACE'])
        self.assertEqual((result.verification_count, result.revision_count), (1, 0))
        self.assertIn('confirmed', h.cg.calls[1]['messages'][1]['content'])  # Context saw the verified event
        self.assertIn('confirmed', h.kg.calls[1]['messages'][1]['content'])

    async def test_context_needs_verification_enters_the_same_bounded_path(self):
        verifier = FakeVerifier(VerificationResult(True, [VERIFIED]))
        needs = context_reply(decision='NEEDS_VERIFICATION', trigger_type=None, material_uncertainty='Stale.',
                              verification_request='Confirm location.', relevance_confidence=0.4)
        h = Harness(context=[needs, context_reply()], critic=[critic_reply()], verifier=verifier)
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, len(verifier.calls), len(h.kg.calls)), (FinalAction.SURFACE, 1, 1))
        self.assertEqual(agents(result), ['CONTEXT', 'VERIFIER', 'CONTEXT', 'CRITIC'])

    async def test_verification_failures_stay_silent(self):
        for name, verifier in (('failed', FakeVerifier(VerificationResult(False, [], 'Sensor unavailable.'))),
                               ('empty', FakeVerifier(VerificationResult(True, []))),
                               ('exception', FakeVerifier(error=RuntimeError('x'))), ('none', None)):
            with self.subTest(name):
                h = Harness(context=[context_reply(), context_reply()], critic=[critic_reply(**VERIFY_CRITIC), critic_reply()], verifier=verifier)
                seed(h.repo)
                result = await h.orch.evaluate_context([DINNER])
                self.assertEqual(result.final_action, FinalAction.STAY_SILENT)
                self.assertEqual((len(h.cg.calls), len(h.kg.calls), result.verification_count), (1, 1, 1))
                self.assertEqual(result.trace_events[-1].action, 'UNVERIFIED')

    async def test_context_still_ambiguous_after_verification_stays_silent(self):
        needs = context_reply(decision='NEEDS_VERIFICATION', trigger_type=None, material_uncertainty='Stale.',
                              verification_request='Confirm location.')
        verifier = FakeVerifier(VerificationResult(True, [VERIFIED]))
        h = Harness(context=[needs, needs], critic=[critic_reply()], verifier=verifier)
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual((result.final_action, len(verifier.calls), h.kg.calls), (FinalAction.STAY_SILENT, 1, []))

    async def test_revision_and_verification_bounds_hold_together(self):
        verifier = FakeVerifier(VerificationResult(True, [VERIFIED]))
        h = Harness(context=[context_reply(), context_reply()], verifier=verifier,
                    critic=[critic_reply(**VERIFY_CRITIC), critic_reply(**REVISION_CRITIC), critic_reply(**VERIFY_CRITIC), critic_reply()],
                    open_loop=[open_loop_reply('REVISE', target_loop_id='loop_carlton', proposed_title='Interested in Brunetti')])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        self.assertEqual(result.final_action, FinalAction.STAY_SILENT)
        self.assertEqual((result.revision_count, result.verification_count), (1, 1))
        self.assertLessEqual((len(h.og.calls), len(verifier.calls), len(h.kg.calls)), (1, 1, 3))
        self.assertEqual(len(h.kg.calls), 3)


class ArtifactTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_is_structured_and_serializable_as_json_and_jsonl(self):
        h = Harness(context=[context_reply()], critic=[critic_reply()])
        seed(h.repo)
        result = await h.orch.evaluate_context([DINNER])
        lines = result.trace_jsonl().splitlines()
        self.assertEqual(len(lines), len(result.trace_events))
        for line, event in zip(lines, result.trace_events):
            parsed = json.loads(line)
            self.assertEqual(parsed['run_id'], result.run_id)
            self.assertEqual(parsed['timestamp'], '2026-10-25T12:00:00+00:00')
            self.assertEqual(set(parsed), {'run_id', 'timestamp', 'agent', 'action', 'reason', 'input_refs', 'next_step', 'output_ref', 'receipt'})
            self.assertEqual(parsed['agent'], event.agent)
        self.assertEqual(json.loads(json.dumps(result.to_dict()))['final_action'], 'SURFACE')
        self.assertEqual(json.loads(lines[-1])['output_ref'], 'loop:loop_carlton')


if __name__ == '__main__':
    unittest.main()
