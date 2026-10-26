"""Offline tests for duplicate review, loop consolidation and the daily Check-in API. No sponsor service or network."""
import asyncio
from contextlib import nullcontext
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.agents.critic import CriticAgent, CriticError, DuplicateKind, parse_duplicate_decisions
from backend.app.domain.models import CheckIn, Entity, LoopEntity, LoopStatus, OpenLoop
from backend.app.main import app
from backend.app.orchestration.consolidation import Consolidator, apply_merge, candidate_pairs, merge_question
from backend.app.repositories.memory import InMemoryLoopRepository

NOW = '2026-10-26T10:00:00+00:00'


class ScriptedGateway:
    reasoning_model = 'test-model'
    def __init__(self, reply):
        self.reply, self.calls, self.last_routing = reply, 0, {}

    async def complete(self, messages, **kwargs):
        self.calls += 1
        self.last_routing = {'requested_model': 'test-model', 'routed_model': 'test-model', 'provider': 'nvidia'}  # like the real gateway
        payload = json.loads(messages[-1]['content'])
        return json.dumps({'pairs': [self.reply(pair, payload) for pair in payload['pairs']]})


def decision(pair, kind, **extra):
    return {'loop_ids': pair, 'decision': kind, 'canonical_loop_id': extra.get('canonical'), 'question': extra.get('question'),
            'confidence': 0.8, 'concise_reason': 'test reason'}


def world():
    repo = InMemoryLoopRepository()
    entities = [Entity('e1', 'product', 'shopping', "Air Jordan 3 'Neo Pink'", brand='Jordan'),
                Entity('e2', 'product', 'shopping', "Air Jordan 3 'Washed Coral'", brand='Jordan'),
                Entity('e3', 'place', 'food', "Charrd Burger", city='Melbourne')]
    for e in entities:
        repo.entities[e.entity_id] = e
    loops = [OpenLoop('l1', "Interested in Air Jordan 3 OG 'Neo Pink' sneakers", 'shopping', LoopStatus.OPEN, 0.7, NOW, '2026-10-26T10:01:00+00:00'),
             OpenLoop('l2', "Interested in Air Jordan 3 'Washed Coral' sneakers", 'shopping', LoopStatus.OPEN, 0.7, NOW, NOW),
             OpenLoop('l3', 'Interested in Charrd burger (Melbourne)', 'food', LoopStatus.OPEN, 0.7, NOW, NOW)]
    for loop, entity in zip(loops, entities):
        repo.save_open_loop(loop)
        repo.link_loop_entity(LoopEntity(loop.loop_id, entity.entity_id, 'subject', 0.7))
    return repo


class Pairing(unittest.TestCase):
    def test_only_look_alikes_in_the_same_domain_are_paired(self):
        repo = world()
        loops = list(repo.loops.values())
        by_loop = {l.loop_id: repo.get_entities([k.entity_id for k in repo.get_loop_entities([l.loop_id])]) for l in loops}
        self.assertEqual(candidate_pairs(loops, by_loop), [('l1', 'l2')])

    def test_one_distinctive_shared_word_is_enough_but_generic_words_are_not(self):
        def loop(i, title, domain='food'):
            return OpenLoop(i, title, domain, LoopStatus.OPEN, 0.7, NOW, NOW)
        loops = [loop('a', "Interested in Elmo's Hamburger Restaurant"), loop('b', "Interested in Elmo's Burgers"),
                 loop('c', 'Interested in OMB Burger (Melbourne CBD)'), loop('d', 'Interested in Charrd burger (Melbourne)'),
                 loop('e', "Alfred Nicholas Garden (~1 hr from CBD)", 'travel')]
        self.assertEqual(candidate_pairs(loops, {}), [('a', 'b')])


class DuplicateParsing(unittest.TestCase):
    def parse(self, *entries, pairs=(('a', 'b'),)):
        return parse_duplicate_decisions(json.dumps({'pairs': list(entries)}), pairs=pairs)

    def test_valid_decisions(self):
        self.assertEqual(self.parse(decision(['b', 'a'], 'ASK', question='Same?'))[0].decision, DuplicateKind.ASK)
        self.assertEqual(self.parse(decision(['a', 'b'], 'MERGE', canonical='a'))[0].canonical_loop_id, 'a')

    def test_rejects_unsafe_output(self):
        bad = [decision(['a', 'zzz'], 'KEEP_SEPARATE'), decision(['a', 'b'], 'MERGE', canonical='zzz'), decision(['a', 'b'], 'MERGE'),
               decision(['a', 'b'], 'ASK'), decision(['a', 'b'], 'KEEP_SEPARATE', question='no'), decision(['a', 'b'], 'DELETE')]
        for entry in bad:
            with self.assertRaises(CriticError):
                self.parse(entry)
        with self.assertRaises(CriticError):  # every offered pair must be answered
            self.parse()


class Consolidation(unittest.TestCase):
    def consolidator(self, repo, reply):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        gateway = ScriptedGateway(reply)
        return Consolidator(CriticAgent(gateway, repo), repo, judged_path=Path(directory.name) / 'judged.json', now=lambda: NOW), gateway

    def test_merge_folds_into_the_canonical_loop_and_hides_the_duplicate(self):
        repo = world()
        consolidator, _ = self.consolidator(repo, lambda pair, payload: decision(pair, 'MERGE', canonical='l1'))
        result = asyncio.run(consolidator.run('2026-10-26', 'run_t'))
        self.assertEqual(result.merged, [('l1', 'l2')])
        self.assertEqual(repo.get_open_loop('l2').status, LoopStatus.INVALIDATED)
        self.assertEqual({k.entity_id for k in repo.get_loop_entities(['l1'])}, {'e1', 'e2'})
        self.assertEqual([l.loop_id for l in repo.get_active_open_loops()], ['l1', 'l3'])
        self.assertTrue(all(e.receipt for e in result.trace_events if e.action == 'MERGE'))

    def test_ask_files_one_check_in_for_today_and_is_not_repeated(self):
        repo = world()
        consolidator, gateway = self.consolidator(repo, lambda pair, payload: decision(pair, 'ASK', question='Are these the same shoe?'))
        result = asyncio.run(consolidator.run('2026-10-26', 'run_t'))
        [item] = repo.get_check_ins(day='2026-10-26', status='PENDING')
        self.assertEqual((item.kind, item.loop_id, item.other_loop_id), ('MERGE_LOOPS', 'l1', 'l2'))
        self.assertEqual(item.question['question'], 'Are these the same shoe?')
        self.assertEqual(result.asked, [item.check_in_id])
        self.assertEqual(repo.get_open_loop('l2').status, LoopStatus.OPEN)  # asking never changes a loop
        again = asyncio.run(consolidator.run('2026-10-26', 'run_t2'))
        self.assertEqual((again.candidate_pairs, gateway.calls), (0, 1))

    def test_keep_separate_is_remembered(self):
        repo = world()
        consolidator, gateway = self.consolidator(repo, lambda pair, payload: decision(pair, 'KEEP_SEPARATE'))
        self.assertEqual(asyncio.run(consolidator.run('2026-10-26', 'r1')).kept_separate, 1)
        self.assertEqual(asyncio.run(consolidator.run('2026-10-27', 'r2')).candidate_pairs, 0)
        self.assertEqual(gateway.calls, 1)

    def test_failed_review_changes_nothing(self):
        repo = world()
        consolidator, _ = self.consolidator(repo, lambda pair, payload: {'loop_ids': pair, 'decision': 'DELETE'})
        result = asyncio.run(consolidator.run('2026-10-26', 'r'))
        self.assertTrue(result.errors)
        self.assertEqual((result.merged, result.asked, repo.get_check_ins()), ([], [], []))
        self.assertEqual({l.status for l in repo.loops.values()}, {LoopStatus.OPEN})

    def test_dry_run_makes_no_model_call(self):
        consolidator, gateway = self.consolidator(world(), lambda pair, payload: decision(pair, 'MERGE', canonical='l1'))
        self.assertEqual(asyncio.run(consolidator.run('2026-10-26', 'r', dry_run=True)).candidate_pairs, 1)
        self.assertEqual(gateway.calls, 0)

    def test_cannot_merge_a_loop_into_itself(self):
        with self.assertRaises(ValueError):
            apply_merge(world(), 'l1', 'l1', NOW)


class CheckInApi(unittest.TestCase):
    def client(self):
        env = patch.dict(os.environ, {'SAMPLE_MODE': 'true'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def seed(self, day):
        repo = app.state.repository
        for loop in world().loops.values():
            repo.save_open_loop(loop)
        for link in world().loop_entities:
            repo.link_loop_entity(link)
        keep, fold = repo.get_open_loop('l1'), repo.get_open_loop('l2')
        question = merge_question(day, keep, fold, 'Same shoe?')
        repo.save_check_in(CheckIn(question['id'], day, 'MERGE_LOOPS', 'l1', 'l2', question, 'PENDING', NOW))
        return question['id']

    def test_serves_only_todays_unanswered_questions(self):
        client = self.client()
        from backend.app.main import _today
        today = self.seed(_today())
        self.seed('2000-01-01')  # an earlier day's question must not carry over
        questions = client.get('/api/check-ins').json()['questions']
        self.assertEqual([q['id'] for q in questions], [today])
        self.assertEqual(questions[0]['positive']['value'], 'same')

    def test_same_merges_and_different_leaves_loops_alone(self):
        client = self.client()
        from backend.app.main import _today
        check_in = self.seed(_today())
        self.assertEqual(client.post(f'/api/check-ins/{check_in}/respond', json={'response': 'maybe'}).status_code, 422)
        self.assertEqual(client.post('/api/check-ins/none/respond', json={'response': 'same'}).status_code, 404)
        self.assertEqual(client.post(f'/api/check-ins/{check_in}/respond', json={'response': 'different'}).status_code, 200)
        self.assertEqual(app.state.repository.get_open_loop('l2').status, LoopStatus.OPEN)
        self.assertEqual(client.get('/api/check-ins').json()['questions'], [])
        self.assertEqual(client.post(f'/api/check-ins/{check_in}/respond', json={'response': 'same'}).status_code, 409)

    def test_confirming_same_thing_merges(self):
        client = self.client()
        from backend.app.main import _today
        check_in = self.seed(_today())
        self.assertEqual(client.post(f'/api/check-ins/{check_in}/respond', json={'response': 'same', 'comment': ' yes '}).status_code, 200)
        self.assertEqual(app.state.repository.get_open_loop('l2').status, LoopStatus.INVALIDATED)
        answered = app.state.repository.get_check_in(check_in)
        self.assertEqual((answered.status, answered.response, answered.comment), ('ANSWERED', 'same', 'yes'))


if __name__ == '__main__':
    unittest.main()
