"""Explicit deterministic demo fixtures. No image analysis, sponsor calls or receipts.

Never use these scripted replies for production. The entrypoint requires
SAMPLE_MODE=true and labels every output as synthetic.
"""
from __future__ import annotations

import json
from contextlib import nullcontext

from backend.app.bootstrap import build_orchestrator, open_repository, sample_mode


class SampleGateway:
    vision_model = 'sample-fixture-no-model'
    reasoning_model = 'sample-fixture-no-model'
    last_routing = {}

    async def complete(self, messages, **kwargs):
        if not sample_mode():
            raise RuntimeError('Scripted fixture gateway requires SAMPLE_MODE=true.')
        payload = json.loads(messages[-1]['content'])
        if 'new_evidence' in payload:
            result = dict(decision='CREATE', target_loop_id=None, proposed_title='Sample interest in a café',
                          domain='food', confidence=0.7, concise_reason='Scripted sample decision; no model was called.',
                          supporting_evidence_ids=[payload['new_evidence']['evidence_id']],
                          supporting_entity_ids=[item['entity_id'] for item in payload['new_entities']], material_uncertainty=None)
        elif 'context_decision' in payload:
            result = dict(decision='SURFACE', loop_id=payload['open_loop']['loop_id'], confidence=0.8,
                          concise_reason='Scripted sample review; no model was called.',
                          supporting_evidence_ids=[item['evidence_id'] for item in payload['supporting_evidence']],
                          supporting_context_ids=[item['context_id'] for item in payload['context_events']],
                          material_uncertainty=None, question=None, revision_request=None, verification_request=None)
        elif 'candidate_open_loops' in payload:
            result = dict(decision='MATCH', candidate_loop_id=payload['candidate_open_loops'][0]['loop_id'],
                          trigger_type='CALENDAR', relevant_context_ids=[payload['context_events'][0]['context_id']],
                          relevance_confidence=0.8, concise_reason='Scripted sample context; no model was called.',
                          material_uncertainty=None, verification_request=None)
        else:
            raise RuntimeError('Unsupported sample fixture request.')
        return json.dumps(result)


async def run_sample(repository=None) -> dict:
    if not sample_mode():
        raise RuntimeError('Set SAMPLE_MODE=true to run the offline fixture example.')
    from backend.app.agents.evidence import Entity, Evidence, Location
    from backend.app.domain.models import ContextEvent, ContextType
    from backend.app.ingestion.evidence_bridge import ingest

    now = lambda: '2026-10-25T10:00:00+00:00'
    scope = nullcontext(repository) if repository is not None else open_repository()
    with scope as repository:
        extraction = Evidence('food', 'Synthetic sample café screenshot fixture; no image was analyzed.',
                              [Entity('Sample café', 'cafe', location=Location('Sample area', 'Melbourne', 'Australia'))], False, 'high')
        graph = ingest(extraction, repository, source='sample_fixture', captured_at=now(), new_id=lambda: 'ev_sample')
        orchestrator = build_orchestrator(SampleGateway(), repository, now=now, new_run_id=lambda: 'run_sample',
                                          new_loop_id=lambda: 'loop_sample')
        await orchestrator.open_loop_agent.process(graph.evidence, graph.entities)
        context = ContextEvent('ctx_sample', ContextType.CALENDAR, 'Synthetic sample café visit', now(), 'Sample area', 'Melbourne', 'Australia')
        result = await orchestrator.evaluate_context([context])
        return {'mode': 'sample', 'data_source': 'synthetic_fixture', 'model_calls': False,
                'repository': 'InMemoryLoopRepository', 'evidence_ids': ['ev_sample'],
                'result': result.to_dict()}
