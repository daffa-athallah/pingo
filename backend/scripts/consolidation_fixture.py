#!/usr/bin/env python3
"""Exercise the Critic's duplicate review with real model calls over a LABELLED FIXTURE (throwaway in-memory repository).

The data has no exact duplicates, so this builds three synthetic pairs: the same venue phrased twice, two plausibly-the-same venues, and two
unrelated venues. The decisions are real Nightshift -> Nemotron output; the expected outcome is not hardcoded. Zetaris is not written to.
"""
import argparse
import asyncio
from pathlib import Path
import tempfile

import real_env
from real_env import ROOT
from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.critic import CriticAgent
from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.orchestration.consolidation import Consolidator
from backend.app.repositories.memory import InMemoryLoopRepository

NOW = '2026-10-26T10:00:00+00:00'
CASES = [  # (loop id, title, entity name, evidence summary)
    ('f1', 'Interested in OMB Burger (halal, late-night, under $10, Melbourne CBD)', 'OMB Burger', 'A promo for OMB Burger, a halal late-night burger spot in Melbourne CBD, under $10.'),
    ('f2', 'Interested in Own My Burger late-night halal burgers', 'OMB Burger', 'A story about OMB Burger serving halal burgers late at night in the Melbourne CBD.'),
    ('f3', "Interested in Elmo's Hamburger Restaurant (Fitzroy North)", "Elmo's Hamburger Restaurant", "A video recommending Elmo's Hamburger Restaurant in Fitzroy North."),
    ('f4', "Interested in Elmo's Burgers", "Elmo's Burgers", "A list of burger places mentioning Elmo's Burgers in Melbourne."),
    ('f5', 'Interested in Yamamoto Udon Izakaya (QV Square, Melbourne)', 'Yamamoto Udon Izakaya', 'Opening hours and food video for Yamamoto Udon Izakaya at QV Square.'),
    ('f6', 'Interested in Yamamoto Cafe Bondi (Sydney)', 'Yamamoto Cafe Bondi', 'A cafe called Yamamoto Cafe in Bondi, Sydney.'),
]


async def run() -> int:
    repo = InMemoryLoopRepository()
    for number, (loop_id, title, name, summary) in enumerate(CASES):
        entity = Entity(f'e_{loop_id}', 'place', 'food', name, city='Melbourne')
        evidence = Evidence(f'ev_{loop_id}', 'fixture', 'food', summary, NOW, False, 'high', None)
        repo.save_evidence(evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', 0.9)])
        repo.save_open_loop(OpenLoop(loop_id, title, 'food', LoopStatus.OPEN, 0.7, NOW, f'2026-10-26T10:0{number}:00+00:00'))
        repo.link_loop_entity(LoopEntity(loop_id, entity.entity_id, 'subject', 0.7))
    print('[FIXTURE] SYNTHETIC loops in a throwaway in-memory repository; Zetaris is not written to')
    with tempfile.TemporaryDirectory() as directory:
        async with ModelGateway.from_env() as gateway:
            consolidator = Consolidator(CriticAgent(gateway, repo), repo, judged_path=Path(directory) / 'judged.json')
            result = await consolidator.run('2026-10-26', 'run_cons_fixture')
    for event in result.trace_events:
        print(f'  {event.agent:8}{event.action:14}receipt={(event.receipt or {}).get("provider")} | {event.reason[:150]}')
    for item in repo.get_check_ins():
        print(f'  CHECK-IN [{item.status}] {item.question["question"]}  (keep {item.loop_id}, fold {item.other_loop_id})')
    print(f'[SUMMARY] pairs={result.candidate_pairs} merged={result.merged} asked={len(result.asked)} kept_separate={result.kept_separate} model_calls={result.model_calls} errors={result.errors}')
    print('active loops after:', sorted(l.loop_id for l in repo.get_active_open_loops()))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, action='append', default=[])
    parser.parse_args()
    try:
        real_env.load_env()
        return asyncio.run(run())
    except ModelGatewayError as exc:
        print('[FAIL]', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
