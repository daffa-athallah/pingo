"""RecallOrchestrator: bounded collaboration between the existing agents.

It is not an agent and makes no model decisions. It sequences Evidence, Open Loop, Context and
Critic, honours their structured outputs, records a trace of exactly what executed, and enforces
hard bounds: at most one Open Loop revision and one context verification per run, and at most one
retry of a failed agent call. Every failure path ends in STORED, STAY_SILENT or FAILED_SAFE; nothing
defaults to SURFACE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence
import uuid

from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.context import ContextAgent, ContextDecision, ContextDecisionKind, ContextError
from backend.app.agents.critic import CriticAgent, CriticDecision, CriticError, CriticKind
from backend.app.agents.evidence import EvidenceAgent, EvidenceError
from backend.app.agents.open_loop import Decision, OpenLoopAgent, OpenLoopError, RevisionRequest
from backend.app.domain import models as m
from backend.app.domain.trace import TraceEvent
from backend.app.ingestion.evidence_bridge import ingest
from backend.app.repositories.base import LoopRepository

MAX_REVISIONS = 1
MAX_VERIFICATIONS = 1
MAX_ATTEMPTS = 2  # one call plus at most one retry
_KNOWN_ERRORS = (EvidenceError, OpenLoopError, ContextError, CriticError, ModelGatewayError)


class RunType(str, Enum):
    EVIDENCE_INGESTION = 'EVIDENCE_INGESTION'
    CONTEXT_EVALUATION = 'CONTEXT_EVALUATION'


class FinalAction(str, Enum):
    STORED = 'STORED'
    SURFACE = 'SURFACE'
    STAY_SILENT = 'STAY_SILENT'
    ASK = 'ASK'
    FAILED_SAFE = 'FAILED_SAFE'


@dataclass(frozen=True)
class VerificationRequest:
    loop_id: str | None
    request: str
    context_ids: list[str]


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    events: list[m.ContextEvent] = field(default_factory=list)
    note: str | None = None


class ContextVerifier(Protocol):
    """Boundary for checking a context trigger (calendar, location, time) against a real source."""

    async def verify(self, request: VerificationRequest, events: Sequence[m.ContextEvent]) -> VerificationResult: ...


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_type: RunType
    final_action: FinalAction
    loop_id: str | None = None
    evidence_id: str | None = None
    message_payload: dict | None = None
    question: str | None = None
    error: str | None = None
    revision_count: int = 0
    verification_count: int = 0
    trace_events: list[TraceEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {'run_id': self.run_id, 'run_type': self.run_type.value, 'final_action': self.final_action.value,
                'loop_id': self.loop_id, 'evidence_id': self.evidence_id, 'message_payload': self.message_payload,
                'question': self.question, 'error': self.error, 'revision_count': self.revision_count,
                'verification_count': self.verification_count, 'trace_events': [e.to_dict() for e in self.trace_events]}

    def trace_jsonl(self) -> str:
        return '\n'.join(json.dumps(e.to_dict(), ensure_ascii=False) for e in self.trace_events)


_CRITIC_NEXT = {'OUTPUT_LAYER': 'OUTPUT', 'STOP': 'STOP', 'CHECK_IN': 'CHECK_IN',
                'OPEN_LOOP_AGENT': 'OPEN_LOOP', 'CONTEXT_AGENT': 'CONTEXT'}


class _Run:
    def __init__(self, run_id: str, run_type: RunType, now: Callable[[], str]):
        self.run_id, self.run_type, self._now = run_id, run_type, now
        self.events: list[TraceEvent] = []
        self.revisions = 0
        self.verifications = 0

    def record(self, agent: str, action: str, reason: str, refs: Sequence[str] = (), next_step: str | None = None,
               output_ref: str | None = None, receipt: dict | None = None) -> None:
        self.events.append(TraceEvent(agent, action, reason, list(refs), next_step, output_ref,
                                      self.run_id, self._now(), receipt))

    def result(self, action: FinalAction, **kw) -> RunResult:
        return RunResult(self.run_id, self.run_type, action, revision_count=self.revisions,
                         verification_count=self.verifications, trace_events=list(self.events), **kw)


def _receipt(gateway) -> dict | None:
    routing = dict(getattr(gateway, 'last_routing', None) or {})
    keys = ('requested_model', 'routed_model', 'provider')
    return {k: routing.get(k) for k in keys} if routing else None


class RecallOrchestrator:
    def __init__(self, evidence_agent: EvidenceAgent, open_loop_agent: OpenLoopAgent, context_agent: ContextAgent,
                 critic_agent: CriticAgent, repository: LoopRepository, verifier: ContextVerifier | None = None, *,
                 now: Callable[[], str] | None = None, new_run_id: Callable[[], str] | None = None):
        self.evidence_agent, self.open_loop_agent = evidence_agent, open_loop_agent
        self.context_agent, self.critic_agent = context_agent, critic_agent
        self.repository, self.verifier = repository, verifier
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat(timespec='seconds'))
        self._new_run_id = new_run_id or (lambda: 'run_' + uuid.uuid4().hex[:12])

    @classmethod
    def from_gateway(cls, gateway: ModelGateway, repository: LoopRepository, verifier: ContextVerifier | None = None, **kw):
        return cls(EvidenceAgent(gateway), OpenLoopAgent(gateway, repository), ContextAgent(gateway, repository),
                   CriticAgent(gateway, repository), repository, verifier, **kw)

    # ---- bounded agent calls -------------------------------------------------------------------------

    async def _call(self, run: _Run, agent: str, gateway, factory: Callable[[], Awaitable], refs: Sequence[str]):
        """Run an agent call with at most one retry. Returns (value, receipt, error). Reasoning calls are pure
        until their result is applied, so retrying is safe."""
        error = None
        for attempt in range(MAX_ATTEMPTS):
            if hasattr(gateway, 'last_routing'):
                gateway.last_routing = {}
            try:
                value = await factory()
                return value, _receipt(gateway), None
            except Exception as exc:  # noqa: BLE001 - converted to a safe, bounded failure below
                error = str(exc) if isinstance(exc, _KNOWN_ERRORS) else f'Unexpected {type(exc).__name__}'
                if attempt + 1 < MAX_ATTEMPTS:
                    run.record(agent, 'RETRY', f'Call failed ({error}); retrying once.', refs, agent)
        run.record(agent, 'FAILED', f'Call failed after retry ({error}).', refs, 'STOP')
        return None, None, error

    # ---- Flow A: new screenshot ----------------------------------------------------------------------

    async def ingest_screenshot(self, image: Path, *, source: str = 'screenshot') -> RunResult:
        run = _Run(self._new_run_id(), RunType.EVIDENCE_INGESTION, self._now)
        image_ref = f'image:{Path(image).name}'
        extraction, receipt, error = await self._call(run, 'EVIDENCE', self.evidence_agent.gateway,
                                                      lambda: self.evidence_agent.observe(Path(image)), [image_ref])
        if extraction is None:
            return run.result(FinalAction.FAILED_SAFE, error=error)  # nothing was persisted
        names = ', '.join(e.name for e in extraction.entities) or 'no named entities'
        run.record('EVIDENCE', 'EXTRACT', f'Extracted {names} from screenshot.', [image_ref], 'INGESTION', receipt=receipt)
        try:
            ingested = ingest(extraction, self.repository, source=source, image_ref=Path(image).name)
        except Exception as exc:  # noqa: BLE001
            run.record('INGESTION', 'FAILED', 'Evidence could not be stored.', [image_ref], 'STOP')
            return run.result(FinalAction.FAILED_SAFE, error=f'Unexpected {type(exc).__name__}')
        evidence_id = ingested.evidence.evidence_id
        run.record('INGESTION', 'STORE', f'Stored evidence with {len(ingested.entities)} entities.', [image_ref],
                   'OPEN_LOOP', f'evidence:{evidence_id}')
        refs = [f'evidence:{evidence_id}'] + [f'entity:{e.entity_id}' for e in ingested.entities]
        decision, receipt, error = await self._call(run, 'OPEN_LOOP', self.open_loop_agent.gateway,
                                                    lambda: self.open_loop_agent.decide(ingested.evidence, ingested.entities), refs)
        if decision is None:  # evidence stays persisted; no loop is invented
            return run.result(FinalAction.FAILED_SAFE, evidence_id=evidence_id, error=error)
        loop = self.open_loop_agent.apply(decision)
        run.record('OPEN_LOOP', decision.decision.value, decision.concise_reason, refs, 'STOP',
                   f'loop:{loop.loop_id}' if loop else None, receipt)
        return run.result(FinalAction.STORED, loop_id=loop.loop_id if loop else None, evidence_id=evidence_id)

    # ---- Flow B: context event -----------------------------------------------------------------------

    async def evaluate_context(self, events: Sequence[m.ContextEvent]) -> RunResult:
        run = _Run(self._new_run_id(), RunType.CONTEXT_EVALUATION, self._now)
        events = list(events)
        return await self._context_stage(run, events)

    async def _context_stage(self, run: _Run, events: list[m.ContextEvent]) -> RunResult:
        refs = [f'context:{e.context_id}' for e in events]
        context, receipt, error = await self._call(run, 'CONTEXT', self.context_agent.gateway,
                                                   lambda: self.context_agent.assess_active(events), refs)
        if context is None:
            return run.result(FinalAction.STAY_SILENT, error=error)
        loop_ref = [f'loop:{context.candidate_loop_id}'] if context.candidate_loop_id else []
        next_step = {ContextDecisionKind.MATCH: 'CRITIC', ContextDecisionKind.NO_MATCH: 'STOP',
                     ContextDecisionKind.NEEDS_VERIFICATION: 'VERIFIER'}[context.decision]
        if context.decision == ContextDecisionKind.NEEDS_VERIFICATION and run.verifications >= MAX_VERIFICATIONS:
            next_step = 'STOP'
        run.record('CONTEXT', context.decision.value, context.concise_reason, refs + loop_ref, next_step,
                   loop_ref[0] if loop_ref else None, receipt)
        if context.decision == ContextDecisionKind.NO_MATCH:
            return run.result(FinalAction.STAY_SILENT)
        if context.decision == ContextDecisionKind.NEEDS_VERIFICATION:
            if run.verifications >= MAX_VERIFICATIONS:
                return run.result(FinalAction.STAY_SILENT, loop_id=context.candidate_loop_id,
                                  error='Context still needs verification after the allowed attempt.')
            return await self._verification(run, context, events)
        return await self._critic_stage(run, context, events)

    async def _critic_stage(self, run: _Run, context: ContextDecision, events: list[m.ContextEvent]) -> RunResult:
        loop_id = context.candidate_loop_id
        refs = [f'loop:{loop_id}'] + [f'context:{i}' for i in context.relevant_context_ids]
        decision, receipt, error = await self._call(run, 'CRITIC', self.critic_agent.gateway,
                                                    lambda: self.critic_agent.review_from_repository(context, events), refs)
        if decision is None:
            return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error=error)
        refs = refs + [f'evidence:{i}' for i in decision.supporting_evidence_ids]
        kind = decision.decision

        def record(next_step: str, reason: str | None = None) -> None:
            out = f'loop:{decision.loop_id}' if kind == CriticKind.SURFACE and decision.loop_id else None
            run.record('CRITIC', kind.value, reason or decision.concise_reason, refs, next_step, out, receipt)

        if kind == CriticKind.REQUEST_REVISION:
            if run.revisions >= MAX_REVISIONS:
                record('STOP', f'{decision.concise_reason} A second revision is not allowed; stopping safely.')
                return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error='Revision limit reached.')
            record('OPEN_LOOP')
            return await self._revision(run, context, events, decision)
        if kind == CriticKind.VERIFY_CONTEXT:
            if run.verifications >= MAX_VERIFICATIONS:
                record('STOP', f'{decision.concise_reason} Verification limit reached; stopping safely.')
                return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error='Verification limit reached.')
            record('CONTEXT')
            return await self._verification(run, context, events, decision.verification_request)
        record(_CRITIC_NEXT[decision.next_step.value])
        if kind == CriticKind.SURFACE:
            loop = self.repository.get_open_loop(decision.loop_id)
            return run.result(FinalAction.SURFACE, loop_id=decision.loop_id, message_payload={
                'loop_id': decision.loop_id, 'title': loop.title if loop else None, 'reason': decision.concise_reason,
                'evidence_ids': decision.supporting_evidence_ids, 'context_ids': decision.supporting_context_ids})
        if kind == CriticKind.ASK:
            return run.result(FinalAction.ASK, loop_id=decision.loop_id, question=decision.question,
                              message_payload={'loop_id': decision.loop_id, 'question': decision.question,
                                               'uncertainty': decision.material_uncertainty})
        return run.result(FinalAction.STAY_SILENT, loop_id=decision.loop_id)

    # ---- Critic -> Open Loop --------------------------------------------------------------------------

    async def _revision(self, run: _Run, context: ContextDecision, events: list[m.ContextEvent],
                        critic: CriticDecision) -> RunResult:
        run.revisions += 1
        loop_id = context.candidate_loop_id
        links = self.repository.get_loop_entities([loop_id])
        entities = self.repository.get_entities(sorted({k.entity_id for k in links}))
        evidence = self.repository.get_related_evidence([e.entity_id for e in entities], limit=1) if entities else []
        if not evidence:
            run.record('OPEN_LOOP', 'FAILED', 'No stored evidence to reconsider the loop with.', [f'loop:{loop_id}'], 'STOP')
            return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error='No evidence available for revision.')
        revision = RevisionRequest(loop_id, critic.revision_request or critic.concise_reason, critic.concise_reason)
        refs = [f'loop:{loop_id}', f'evidence:{evidence[0].evidence_id}']
        decision, receipt, error = await self._call(run, 'OPEN_LOOP', self.open_loop_agent.gateway,
                                                    lambda: self.open_loop_agent.decide(evidence[0], entities, revision), refs)
        if decision is None:
            return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error=error)
        if decision.decision != Decision.REVISE:
            run.record('OPEN_LOOP', decision.decision.value, decision.concise_reason, refs, 'STOP', None, receipt)
            return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error='Loop was not revised.')
        loop = self.open_loop_agent.apply(decision)
        run.record('OPEN_LOOP', 'REVISE', decision.concise_reason, refs, 'CRITIC', f'loop:{loop.loop_id}', receipt)
        return await self._critic_stage(run, context, events)

    # ---- Critic/Context -> verifier -> Context --------------------------------------------------------

    async def _verification(self, run: _Run, context: ContextDecision, events: list[m.ContextEvent],
                            request_text: str | None = None) -> RunResult:
        run.verifications += 1
        loop_id = context.candidate_loop_id
        refs = ([f'loop:{loop_id}'] if loop_id else []) + [f'context:{i}' for i in context.relevant_context_ids]
        request = VerificationRequest(loop_id, request_text or context.verification_request or context.concise_reason,
                                      list(context.relevant_context_ids))
        result = None
        if self.verifier is not None:
            try:
                result = await self.verifier.verify(request, events)
            except Exception:  # noqa: BLE001
                result = None
        if result is None or not result.verified or not result.events:
            run.record('VERIFIER', 'UNVERIFIED', (result.note if result and result.note else 'Context could not be verified.'),
                       refs, 'STOP')
            return run.result(FinalAction.STAY_SILENT, loop_id=loop_id, error='Context was not verified.')
        run.record('VERIFIER', 'VERIFIED', result.note or 'Context verified.', refs, 'CONTEXT')
        return await self._context_stage(run, list(result.events))
