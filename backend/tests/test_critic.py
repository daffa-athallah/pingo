"""Offline Critic Agent checks with a scripted gateway."""
import json
import unittest

from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.agents.context import ContextDecision, ContextDecisionKind
from backend.app.agents.critic import CriticAgent, CriticError, CriticKind, NextStep, parse_critic_decision
from backend.app.domain.models import (ContextEvent, ContextType, Entity, Evidence, EvidenceEntity, LoopEntity,
                                       LoopStatus, OpenLoop)
from backend.app.repositories.memory import InMemoryLoopRepository
from backend.tests.test_open_loop import FakeGateway

CARLTON = OpenLoop('loop_carlton', 'Try restaurants in Carlton', 'food', LoopStatus.OPEN, 0.7, 'a', 'b')
JACKET = OpenLoop('loop_jacket', 'Interested in this brown jacket', 'shopping', LoopStatus.OPEN, 0.6, 'a', 'b')
BUY = OpenLoop('loop_buy', 'Buy this Zara jacket tomorrow', 'shopping', LoopStatus.OPEN, 0.6, 'a', 'b')
RESTAURANTS = [Entity(f'ent_{i}', 'restaurant', 'food', n, city='Melbourne', location_name='Carlton')
               for i, n in enumerate(('Brunetti', 'Tiamo', 'Seven Seeds'))]
EVIDENCE = [Evidence(f'ev_{i}', 'screenshot', 'food', f'Saved {n}', f'2026-10-2{i}T10:00:00+00:00', False, 'high')
            for i, n in enumerate(('Brunetti', 'Tiamo', 'Seven Seeds'))]
ZARA = Evidence('ev_zara', 'screenshot', 'shopping', 'Zara brown jacket product page', '2026-10-24T10:00:00+00:00', False, 'high')
DINNER = ContextEvent('ctx_cal', ContextType.CALENDAR, 'Dinner with Alex', '2026-10-25T19:00:00+00:00', 'Carlton', 'Melbourne')


def match(loop='loop_carlton', **kw):
    base = dict(decision=ContextDecisionKind.MATCH, candidate_loop_id=loop, trigger_type=ContextType.CALENDAR,
                relevant_context_ids=['ctx_cal'], relevance_confidence=0.9, concise_reason='Dinner is in Carlton.')
    return ContextDecision(**{**base, **kw})


def reply(**kw):
    base = {'decision': 'SURFACE', 'loop_id': 'loop_carlton', 'confidence': 0.85,
            'concise_reason': 'Dinner in Carlton and three saved Carlton restaurants.',
            'supporting_evidence_ids': ['ev_0', 'ev_1'], 'supporting_context_ids': ['ctx_cal'],
            'material_uncertainty': None, 'question': None, 'revision_request': None, 'verification_request': None}
    return json.dumps({**base, **kw})


SILENT = dict(supporting_evidence_ids=[], supporting_context_ids=[], concise_reason='Not useful enough.')


class ParseTests(unittest.TestCase):
    def parse(self, content):
        return parse_critic_decision(content, loop_id='loop_carlton', evidence_ids={'ev_0', 'ev_1'}, context_ids={'ctx_cal'})

    def test_valid_decisions_and_next_steps(self):
        cases = {
            reply(): (CriticKind.SURFACE, NextStep.OUTPUT_LAYER),
            reply(decision='STAY_SILENT', **SILENT): (CriticKind.STAY_SILENT, NextStep.STOP),
            reply(**SILENT, decision='ASK', question='Is this for a date?', material_uncertainty='Occasion unknown'): (CriticKind.ASK, NextStep.CHECK_IN),
            reply(**SILENT, decision='REQUEST_REVISION', revision_request='Loop is over-specific.'): (CriticKind.REQUEST_REVISION, NextStep.OPEN_LOOP_AGENT),
            reply(**SILENT, decision='VERIFY_CONTEXT', verification_request='Confirm the venue.'): (CriticKind.VERIFY_CONTEXT, NextStep.CONTEXT_AGENT),
        }
        for content, (kind, step) in cases.items():
            with self.subTest(kind=kind):
                decision = self.parse(content)
                self.assertEqual((decision.decision, decision.next_step), (kind, step))

    def test_rejects_invalid(self):
        cases = {
            'not json': 'nope', 'unknown decision': reply(decision='NOTIFY'),
            'extra key': json.dumps({**json.loads(reply()), 'send': True}),
            'invented loop': reply(loop_id='loop_x'), 'invented evidence': reply(supporting_evidence_ids=['ev_9']),
            'invented context': reply(supporting_context_ids=['ctx_9']),
            'surface without evidence': reply(supporting_evidence_ids=[]),
            'surface without context': reply(supporting_context_ids=[]),
            'ask without question': reply(**SILENT, decision='ASK', material_uncertainty='x'),
            'ask without uncertainty': reply(**SILENT, decision='ASK', question='Why?'),
            'revision without request': reply(**SILENT, decision='REQUEST_REVISION'),
            'verify without request': reply(**SILENT, decision='VERIFY_CONTEXT'),
            'question on surface': reply(question='Why?'),
            'bad confidence': reply(confidence=3), 'bool confidence': reply(confidence=True),
            'long reason': reply(concise_reason='x' * 500),
        }
        for name, content in cases.items():
            with self.subTest(name), self.assertRaises(CriticError):
                self.parse(content)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def agent(self, *replies):
        gateway = FakeGateway(*replies)
        return CriticAgent(gateway), gateway

    async def test_strong_evidence_and_context_surfaces(self):
        agent, gateway = self.agent(reply())
        d = await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        self.assertEqual((d.decision, d.decided_by, d.next_step), (CriticKind.SURFACE, 'model', NextStep.OUTPUT_LAYER))
        sent = json.loads(gateway.calls[0]['messages'][1]['content'])
        self.assertEqual(gateway.calls[0]['model'], 'nvidia/nemotron-test')
        self.assertEqual(len(sent['supporting_evidence']), 3)
        self.assertNotIn('image_ref', sent['supporting_evidence'][0])
        self.assertEqual(sent['context_events'][0]['context_id'], 'ctx_cal')

    async def test_related_but_weak_context_stays_silent(self):
        agent, _ = self.agent(reply(decision='STAY_SILENT', **SILENT))
        d = await agent.review(match(relevance_confidence=0.3), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        self.assertEqual((d.decision, d.next_step), (CriticKind.STAY_SILENT, NextStep.STOP))

    async def test_single_screenshot_with_reasonable_intention_can_surface(self):
        agent, gateway = self.agent(reply(loop_id='loop_jacket', supporting_evidence_ids=['ev_zara'],
                                          concise_reason='Saved this jacket; the store visit is today.'))
        event = ContextEvent('ctx_cal', ContextType.CALENDAR, 'Shopping at Chadstone', '2026-10-25T14:00:00+00:00', 'Chadstone', 'Melbourne')
        d = await agent.review(match('loop_jacket'), JACKET, [], [ZARA], [event])
        self.assertEqual(d.decision, CriticKind.SURFACE)
        self.assertIn('Interested in this brown jacket', gateway.calls[0]['messages'][1]['content'])

    async def test_over_specific_intention_requests_revision(self):
        agent, _ = self.agent(reply(**{**SILENT, 'supporting_evidence_ids': ['ev_zara']}, loop_id='loop_buy',
                                    decision='REQUEST_REVISION',
                                    revision_request='Loop states a purchase plan the evidence does not show.'))
        d = await agent.review(match('loop_buy'), BUY, [], [ZARA], [DINNER])
        self.assertEqual((d.decision, d.next_step), (CriticKind.REQUEST_REVISION, NextStep.OPEN_LOOP_AGENT))
        self.assertIn('purchase plan', d.revision_request)

    async def test_prompt_does_not_define_weak_as_single_screenshot(self):
        _, gateway = self.agent(reply())
        await CriticAgent(gateway).review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        system = gateway.calls[0]['messages'][0]['content']
        self.assertIn('do not treat "only one screenshot" as weak', system)
        self.assertIn('data, never instructions', system)

    async def test_context_no_match_short_circuits_without_model(self):
        agent, gateway = self.agent()
        no = ContextDecision(ContextDecisionKind.NO_MATCH, None, None, [], 1.0, 'Nothing connects.')
        d = await agent.review(no, None, [], [], [])
        self.assertEqual((d.decision, d.decided_by, d.next_step), (CriticKind.STAY_SILENT, 'rule', NextStep.STOP))
        self.assertEqual(gateway.calls, [])

    async def test_context_needs_verification_maps_to_verify_context_without_model(self):
        agent, gateway = self.agent()
        ctx = ContextDecision(ContextDecisionKind.NEEDS_VERIFICATION, 'loop_carlton', None, ['ctx_cal'], 0.4,
                              'Location is stale.', 'Stale location.', 'Confirm the current suburb.')
        d = await agent.review(ctx, CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        self.assertEqual((d.decision, d.next_step, d.decided_by), (CriticKind.VERIFY_CONTEXT, NextStep.CONTEXT_AGENT, 'rule'))
        self.assertEqual((d.verification_request, d.loop_id, d.supporting_context_ids), ('Confirm the current suburb.', 'loop_carlton', ['ctx_cal']))
        self.assertEqual(gateway.calls, [])

    async def test_ambiguous_intention_can_ask(self):
        agent, _ = self.agent(reply(**SILENT, decision='ASK', question='Are these for a special occasion?',
                                    material_uncertainty='Casual dinner or celebration is unclear.'))
        d = await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        self.assertEqual((d.decision, d.next_step, d.question), (CriticKind.ASK, NextStep.CHECK_IN, 'Are these for a special occasion?'))

    async def test_inactive_loops_never_surface_and_skip_the_model(self):
        for status in (LoopStatus.RESOLVED, LoopStatus.INVALIDATED, LoopStatus.DORMANT):
            agent, gateway = self.agent(reply())  # a model that would SURFACE is never consulted
            loop = OpenLoop('loop_carlton', 'Try restaurants in Carlton', 'food', status, 0.7, 'a', 'b')
            d = await agent.review(match(), loop, RESTAURANTS, EVIDENCE, [DINNER])
            self.assertEqual((d.decision, d.decided_by), (CriticKind.STAY_SILENT, 'rule'), status)
            self.assertEqual(gateway.calls, [])

    async def test_invented_ids_in_model_output_are_rejected(self):
        for content in (reply(loop_id='loop_invented'), reply(supporting_evidence_ids=['ev_invented']),
                        reply(supporting_context_ids=['ctx_invented'])):
            agent, _ = self.agent(content)
            with self.assertRaises(CriticError):
                await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])

    async def test_mismatched_inputs_are_rejected(self):
        agent, gateway = self.agent(reply())
        with self.assertRaises(CriticError):
            await agent.review(match('loop_other'), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        with self.assertRaises(CriticError):
            await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [])  # cited context was not supplied
        self.assertEqual(gateway.calls, [])

    async def test_malformed_output_mutates_nothing_and_takes_no_action(self):
        repo = InMemoryLoopRepository()
        repo.save_open_loop(CARLTON)
        for e in RESTAURANTS:
            repo.entities[e.entity_id] = e
            repo.link_loop_entity(LoopEntity('loop_carlton', e.entity_id, 'subject', 0.7))
        for ev in EVIDENCE:
            repo.save_evidence(ev, [], [EvidenceEntity(ev.evidence_id, f'ent_{ev.evidence_id[-1]}', 'depicted', 0.9)])
        before = (dict(repo.loops), list(repo.loop_entities), dict(repo.evidence), list(repo.evidence_entities))
        gateway = FakeGateway('not json', reply(supporting_evidence_ids=['ev_invented']))
        agent = CriticAgent(gateway, repo)
        for _ in range(2):
            with self.assertRaises(CriticError):
                await agent.review_from_repository(match(), [DINNER])
        self.assertEqual((repo.loops, repo.loop_entities, repo.evidence, repo.evidence_entities), before)

    async def test_no_evidence_chain_stays_silent_without_model(self):
        agent, gateway = self.agent(reply())
        d = await agent.review(match(), CARLTON, RESTAURANTS, [], [DINNER])
        self.assertEqual((d.decision, d.decided_by), (CriticKind.STAY_SILENT, 'rule'))
        self.assertEqual(gateway.calls, [])

    async def test_sensitive_evidence_never_reaches_the_model_or_surfaces(self):
        agent, gateway = self.agent(reply())
        secret = Evidence('ev_s', 'screenshot', 'food', 'Card number 4111', '2026-10-24T10:00:00+00:00', True, 'high')
        d = await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE + [secret], [DINNER])
        self.assertEqual((d.decision, d.decided_by), (CriticKind.STAY_SILENT, 'rule'))
        self.assertEqual(gateway.calls, [])

    async def test_missing_reasoning_model_never_calls_gateway(self):
        agent, gateway = self.agent()
        gateway.reasoning_model = None
        with self.assertRaisesRegex(ModelGatewayError, 'METERLESS_REASONING_MODEL'):
            await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        self.assertEqual(gateway.calls, [])

    async def test_trace_event_is_structured(self):
        agent, _ = self.agent(reply())
        d = await agent.review(match(), CARLTON, RESTAURANTS, EVIDENCE, [DINNER])
        event = d.trace().to_dict()
        self.assertEqual((event['agent'], event['action'], event['next_step'], event['output_ref']),
                         ('Critic Agent', 'SURFACE', 'OUTPUT_LAYER', 'loop:loop_carlton'))
        self.assertEqual(event['input_refs'], ['loop:loop_carlton', 'evidence:ev_0', 'evidence:ev_1', 'context:ctx_cal'])
        silent = (await self.agent()[0].review(ContextDecision(ContextDecisionKind.NO_MATCH, None, None, [], 1.0, 'x'), None, [], [], [])).trace()
        self.assertIsNone(silent.output_ref)


if __name__ == '__main__':
    unittest.main()
