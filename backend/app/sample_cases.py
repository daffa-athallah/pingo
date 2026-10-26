"""Bundled judge cases. Fixed inputs and clock; unchanged agents parse and validate replies.

Each replay gets a fresh snapshot so repeated cases cannot contaminate each other or
the browsing workspace. Synthetic screenshots/context/over-specific revision fixture
are explicitly labelled. Recorded H-MEM I/O is replayed, never run as a fake engine.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace

from backend.app.bootstrap import build_orchestrator
from backend.app.demo_workspace import open_demo_repository
from backend.app.domain.models import ContextEvent, ContextType, LoopStatus
from backend.app.hmem import HMemRepository
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.observe import ObservedGateway, ObservedRepository, UploadObserver
from backend.app.recorded import DIRECTORY, RecordedGateway, load_recording
from backend.app.runs import RunStore

CASES = {
    'attach': "Elmo's: another screenshot → ATTACH",
    'create': 'Kiwami: a new venue → CREATE',
    'sensitive': 'Synthetic sensitive screenshot → IGNORE',
    'surface': 'Dinner with Alex → relevance',
    'restraint': 'Pick up dry cleaning → restraint',
    'revision': 'Over-specific loop fixture → bounded revision',
    'duplicates': 'Synthetic look-alike fixture → review / Check-in',
}
NOW = '2026-10-26T06:00:00+00:00'
IMAGES = DIRECTORY / 'images'


class MemoryTape:
    def __init__(self, calls=None, inner=None):
        self.calls, self.inner, self.position = calls if calls is not None else [], inner, 0

    def _call(self, method, args):
        if self.inner is not None:
            result = getattr(self.inner, method)(*args)
            self.calls.append({'method': method, 'args': list(args), 'result': result})
            return result
        if self.position >= len(self.calls):
            raise ValueError('Memory recording exhausted.')
        call = self.calls[self.position]
        if call['method'] != method or call['args'] != list(args):
            raise ValueError('Memory input differs from the recording.')
        self.position += 1
        return call['result']

    def query(self, text):
        return self._call('query', (text,))

    def add(self, memory):
        return self._call('add', (memory,))


async def execute_case(case, gateway, *, memory=None, provenance='recorded', now=NOW, capture=None):
    if case not in CASES:
        raise ValueError('Unknown recorded case.')
    repository = open_demo_repository()
    # Controlled revision fixture: same historical evidence, deliberately unsupported title.
    if case == 'revision':
        target = 'loop_11fcb461ff69'
        repository.loops = {target: replace(repository.loops[target], title='Book a table at OMB Burger tonight at 8pm', status=LoopStatus.OPEN)}
        repository.loop_entities = [k for k in repository.loop_entities if k.loop_id == target]
    if case == 'duplicates':
        import json
        from backend.app.domain.models import Entity, Evidence, EvidenceEntity, LoopEntity, OpenLoop
        from backend.app.repositories.memory import InMemoryLoopRepository
        repository = InMemoryLoopRepository()
        fixture = json.loads((DIRECTORY / 'duplicate_input.json').read_text())
        for number, (loop_id, title, name, summary) in enumerate(fixture['loops']):
            entity = Entity(f'e_{loop_id}', 'place', 'food', name, city='Melbourne')
            evidence = Evidence(f'ev_{loop_id}', 'fixture', 'food', summary, now, False, 'high')
            repository.save_evidence(evidence, [entity], [EvidenceEntity(evidence.evidence_id, entity.entity_id, 'depicted', 0.9)])
            repository.save_open_loop(OpenLoop(loop_id, title, 'food', LoopStatus.OPEN, 0.7, now, f'2026-10-26T06:0{number}:00+00:00'))
            repository.link_loop_entity(LoopEntity(loop_id, entity.entity_id, 'subject', 0.7))
    store = RunStore('sample')
    recorder = store.start('run_sample_' + case, kind='recorded_sample', provenance=provenance,
                           run_type='EVIDENCE_INGESTION' if case in ('attach', 'create', 'sensitive') else 'CONTEXT_EVALUATION',
                           label=CASES[case], synthetic_inputs=True)
    observer = UploadObserver(recorder, repository, image_ref=f'{case}.png', workspace='sample')
    observed_gateway = ObservedGateway(gateway, observer)
    observed_repository = ObservedRepository(repository, observer)
    agent_repository = HMemRepository(observed_repository, memory, listener=observer.memory_event) if memory is not None else observed_repository
    orchestrator = build_orchestrator(observed_gateway, agent_repository, now=lambda: now,
                                      new_run_id=lambda: recorder.run_id, new_loop_id=lambda: 'loop_sample_' + case)
    observer.wrap_decide(orchestrator.open_loop_agent)
    if case in ('attach', 'create', 'sensitive'):
        # Existing agent/ingestion APIs expose ID and clock injection; no global monkeypatches.
        from backend.app.orchestration.recall import _Run, RunType
        bounded = _Run(recorder.run_id, RunType.EVIDENCE_INGESTION, lambda: now)
        extraction, _, error = await orchestrator._call(bounded, 'EVIDENCE', observed_gateway,
                                                      lambda: orchestrator.evidence_agent.observe(IMAGES / f'{case}.png'), [])
        if extraction is None:
            raise ValueError(error)
        for event in bounded.events:
            recorder.emit(event.agent, event.action, event.reason, next_step=event.next_step)
        bounded.events.clear()
        graph = ingest(extraction, agent_repository, image_ref=f'{case}.png', captured_at=now, new_id=lambda: 'ev_sample_' + case)
        decision, _, error = await orchestrator._call(bounded, 'OPEN_LOOP', observed_gateway,
                                                     lambda: orchestrator.open_loop_agent.decide(graph.evidence, graph.entities), [])
        for event in bounded.events:
            recorder.emit(event.agent, event.action, event.reason, next_step=event.next_step)
        if decision is None:
            raise ValueError(error)
        loop = orchestrator.open_loop_agent.apply(decision)
        result = SimpleNamespace(loop_id=loop.loop_id if loop else None)
        change = observer.outcome(result)
        from backend.app.upload_api import _evidence_view, _loop_view
        recorder.record['outcome'] = {'status': 'stored', 'evidence': _evidence_view(repository, graph.evidence.evidence_id),
                                     'open_loop': {'decision': decision.decision.value, 'reason': decision.concise_reason,
                                                   'confidence': decision.confidence, 'loop': _loop_view(repository, result.loop_id), 'change': change},
                                     'receipts': [], 'error': None}
        if not extraction.sensitive:
            recorder.record['outcome']['evidence']['image_url'] = f'/api/sample/cases/{case}/image'
        recorder.finish('STORED', evidence_id=graph.evidence.evidence_id, loop_id=result.loop_id)
    elif case == 'duplicates':
        from backend.app.orchestration.consolidation import Consolidator
        with tempfile.TemporaryDirectory(prefix='recall-sample-') as directory:
            result = await Consolidator(orchestrator.critic_agent, repository, judged_path=Path(directory) / 'judged.json', now=lambda: now).run(now[:10], recorder.run_id)
        for event in result.trace_events:
            # The existing consolidation trace hardcodes Zetaris; report actual sample storage.
            agent = 'REPOSITORY' if event.agent == 'ZETARIS' else event.agent
            reason = event.reason.replace('from Zetaris', 'from the recorded in-memory snapshot')
            recorder.emit(agent, event.action, reason, input_refs=event.input_refs, next_step=event.next_step,
                          output_ref=event.output_ref, receipt=event.receipt)
        recorder.record['check_ins'] = [q.question for q in repository.get_check_ins()]
        recorder.record['consolidation'] = {k: v for k, v in result.to_dict().items() if k != 'trace_events'}
        recorder.finish('FAILED_SAFE' if result.errors else 'ASK' if result.asked else 'STAY_SILENT', error='; '.join(result.errors) or None)
    else:
        event = ContextEvent('ctx_sample_' + case, ContextType.CALENDAR,
                             'Pick up dry cleaning' if case == 'restraint' else 'Dinner with Alex',
                             '2026-10-26T20:00:00+11:00',
                             'Melbourne CBD' if case == 'revision' else 'Fitzroy North', 'Melbourne', 'Australia')
        # Context and Critic use their own trace, without ingestion-specific hooks.
        orchestrator = build_orchestrator(gateway, repository, now=lambda: now, new_run_id=lambda: recorder.run_id)
        result = await orchestrator.evaluate_context([event])
        recorder.record['context_events'] = [event.__dict__]
        recorder.record['result'] = result.to_dict()
        from backend.app.context_api import _surface
        recorder.record['surface'] = _surface(result, repository, [event])
        recorder.finish(result.final_action.value, error=result.error)
    if 'outcome' in recorder.record:
        recorder.record['outcome']['receipts'] = [{'agent': e['agent'], 'action': e['action'], 'receipt': e['receipt']} for e in recorder.record['result']['trace_events'] if e.get('receipt')]
    recorder.record['started_at'] = recorder.record['finished_at'] = now
    for event in recorder.record['result']['trace_events']:
        event['timestamp'] = now
    if capture is not None:
        capture.append(repository)  # the case's own copy of the history after the agents ran, for the product UI
    recorder.record['recording_note'] = 'Recorded real run, replayed. Synthetic test inputs; no live models or memory engine called during replay.'
    return recorder.record


async def replay_case(case, capture=None):
    recording = load_recording(case)
    gateway = RecordedGateway(recording)
    memory = MemoryTape(recording['memory_calls']) if recording.get('memory_calls') else None
    record = await execute_case(case, gateway, memory=memory, now=recording['clock'], capture=capture)
    gateway.assert_consumed()
    if memory is not None and memory.position != len(memory.calls):
        raise ValueError('Replay did not consume every memory response.')
    record['captured_at'] = recording['captured_at']
    return record
