"""Context evaluation and delivery composition. No prompts, model IDs or agent branches are changed."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

from backend.app.adapters.nightshift import ModelGateway
from backend.app.bootstrap import build_orchestrator
from backend.app.context.geography import located_entity
from backend.app.domain.models import ContextType, LoopStatus
from backend.app.domain.trace import TraceEvent
from backend.app.repositories.context_store import ContextEvaluation, Notification

ACTIVE = {LoopStatus.OPEN, LoopStatus.ACTIVE}
TERMINAL_FEEDBACK = {'DONE', 'NOT_RELEVANT', 'JUST_INSPIRATION'}


class ContextConflict(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timezone-aware timestamp required.')
    return result


class CandidateRepository:
    """Repository view for candidate retrieval; all writes use the original repository.

    This is deterministic retrieval, not an alternative context/critic workflow.
    The unchanged orchestrator still owns retries, verification and revisions.
    """
    def __init__(self, repository, allowed):
        self.repository, self.allowed = repository, set(allowed)

    def __getattr__(self, name):
        return getattr(self.repository, name)

    def get_active_open_loops(self, *, limit=10):
        return [l for l in self.repository.get_active_open_loops(limit=10000) if l.loop_id in self.allowed][:limit]


class ContextService:
    def __init__(self, repository, *, gateway_factory=ModelGateway.from_env, clock=utcnow):
        self.repository, self.gateway_factory, self.clock = repository, gateway_factory, clock
        self.lock = asyncio.Lock()
        self.cooldown = int(os.environ.get('PINGO_NOTIFICATION_COOLDOWN_SECONDS', '21600'))
        self.snooze = int(os.environ.get('PINGO_SNOOZE_SECONDS', '86400'))
        self.strong = float(os.environ.get('PINGO_NEARBY_STRONG_METERS', '500'))
        self.moderate = float(os.environ.get('PINGO_NEARBY_MAX_METERS', '1000'))
        if not (0 < self.strong <= self.moderate and self.cooldown >= 0 and self.snooze > 0):
            raise ValueError('Invalid context threshold configuration.')

    def scope(self):
        return getattr(self.repository, 'unit_of_work', nullcontext)()

    def _blocked(self, loop_id, notifications=None):
        # Use actual delivery time, never a client-controlled simulated clock.
        for n in self.repository.list_notifications() if notifications is None else notifications:
            if n.loop_id != loop_id:
                continue
            p = n.payload
            if p.get('feedback') in TERMINAL_FEEDBACK:
                return 'user_feedback'
            if p.get('snoozed_until') and aware(p['snoozed_until']) > self.clock():
                return 'snoozed'
            if (self.clock() - aware(n.created_at)).total_seconds() < self.cooldown:
                return 'cooldown'
        return None

    def candidates(self, events):
        repo = self.repository
        loops = repo.get_active_open_loops(limit=10000)
        links = repo.get_loop_entities([l.loop_id for l in loops])
        entities = {e.entity_id: e for e in repo.get_entities(sorted({k.entity_id for k in links}))}
        by_entity = None
        if hasattr(repo, 'list_evidence') and hasattr(repo, 'get_evidence_entities'):
            # Real JDBC reads are slow: load the grounding graph in two queries,
            # without a stale cache or one database trip per candidate loop.
            from collections import defaultdict
            by_entity = defaultdict(list)
            all_evidence = {e.evidence_id: e for e in repo.list_evidence()}
            for link in repo.get_evidence_entities(list(all_evidence)):
                if link.evidence_id in all_evidence:
                    by_entity[link.entity_id].append(all_evidence[link.evidence_id])
        locations = [e for e in events if e.context_type == ContextType.LOCATION]
        semantic = any(e.context_type in {ContextType.CALENDAR, ContextType.TIME} for e in events)
        notifications = repo.list_notifications()
        pending_questions = [q for q in repo.get_check_ins() if q.status == 'PENDING' or
                             (q.kind == 'AGENT_CLARIFICATION' and q.response == 'not_sure' and q.answered_at
                              and self.clock() - aware(q.answered_at) < timedelta(hours=24))] if hasattr(repo, 'get_check_ins') else []
        candidates, diagnostics = [], []
        for loop in loops:
            linked = [entities[k.entity_id] for k in links if k.loop_id == loop.loop_id and k.entity_id in entities]
            evidence = ([e for entity in linked for e in by_entity[entity.entity_id]] if by_entity is not None
                        else repo.get_related_evidence([e.entity_id for e in linked], limit=10000))
            # Never expose sensitive loop titles, entity names or evidence to the simulator/models.
            if not evidence or any(e.sensitive for e in evidence):
                continue
            blocked = self._blocked(loop.loop_id, notifications)
            if any(q.kind == 'AGENT_CLARIFICATION' and (q.loop_id == loop.loop_id or
                   set(q.question.get('_entity_ids', [])) & {entity.entity_id for entity in linked}) for q in pending_questions):
                blocked = blocked or 'awaiting_clarification'
            if any(n.loop_id == loop.loop_id and set(n.payload.get('context_ids', ())) & {e.context_id for e in events} for n in notifications):
                blocked = blocked or 'context_already_notified'
            geo = [located_entity(entity, event, self.strong, self.moderate) for entity in linked for event in locations]
            proximity = any(g['match'] in {'strong', 'moderate'} for g in geo)
            eligible = not blocked and (semantic or proximity)
            diagnostics.append({'loop_id': loop.loop_id, 'title': loop.title, 'eligible': eligible,
                                'exclusion': blocked or (None if eligible else 'no_verified_nearby_location'), 'geography': geo})
            if eligible:
                candidates.append(loop.loop_id)
        from backend.app.agents.context import MAX_LOOPS
        for diagnostic in diagnostics:
            if diagnostic['eligible'] and diagnostic['loop_id'] not in candidates[:MAX_LOOPS]:
                diagnostic.update(eligible=False, exclusion='existing_context_agent_candidate_limit')
        return candidates[:MAX_LOOPS], diagnostics

    def _events(self, request, stored):
        events = [e.to_event() for e in request.events]
        # A time tick may reconsider previously submitted calendar context, not invent it.
        if any(e.context_type == ContextType.TIME for e in events):
            simulated = all(e.source.value == 'SIMULATED' for e in request.events)
            known = {e.context_id for e in events}
            for event in stored:
                try:
                    same_mode = (event.metadata.get('source') == 'SIMULATED') == simulated
                    start = aware(event.metadata.get('start_time', ''))
                    end = aware(event.metadata.get('end_time', ''))
                    if event.context_type == ContextType.CALENDAR and same_mode and event.context_id not in known and end >= request.now and start <= request.now + timedelta(days=14):
                        events.append(event)
                except ValueError:
                    continue
        return events

    async def evaluate(self, request):
        async with self.lock:
            repo = self.repository
            evaluation_id = request.fingerprint()
            prior = repo.get_context_evaluation(evaluation_id)
            if prior:
                if prior.payload.get('state') == 'RUNNING':
                    raise ContextConflict('This evaluation is already running or was interrupted. Submit a new context ID to retry.')
                return {**prior.payload, 'replayed': True}
            stored = repo.get_context_events()
            old = {e.context_id: e for e in stored}
            for item in request.events:
                if item.context_id in old and old[item.context_id] != item.to_event():
                    raise ContextConflict('A context ID already exists with different input. Create a new context ID.')
            events = self._events(request, stored)
            stamp = self.clock().isoformat()
            with self.scope():
                for event in events:
                    if event.context_id not in old:
                        repo.save_context_event(event)
                repo.save_context_evaluation(ContextEvaluation(evaluation_id, stamp, {'state': 'RUNNING'}))
            try:
                allowed, diagnostics = self.candidates(events)
                geo = {d['loop_id']: d['geography'] for d in diagnostics if d['eligible']}
                enriched = [replace(e, metadata={**e.metadata, 'geographic_retrieval': json.dumps(geo),
                             'inventory_policy': 'No product inventory has been verified. A verified brand/store location does not imply stock.'}) for e in events]
                view = CandidateRepository(repo, allowed)
                # No gateway is needed when no candidates exist: ContextAgent's native NO_MATCH rule.
                if allowed:
                    async with self.gateway_factory() as gateway:
                        result = await build_orchestrator(gateway, view, now=lambda: request.now.isoformat()).evaluate_context(enriched)
                        expected_model = gateway.reasoning_model
                else:
                    class NoCalls:
                        reasoning_model = None
                    result = await build_orchestrator(NoCalls(), view, now=lambda: request.now.isoformat()).evaluate_context(enriched)
                    expected_model = None
                notification, delivery = self._approved(result, events, allowed, expected_model, stamp)
                check_in_id, check_in_error = None, None
                if result.final_action.value == 'ASK':
                    try:
                        from backend.app.checkin_clarifications import after_critic
                        check_in_id = after_critic(repo, result, clock=self.clock)
                    except Exception:
                        check_in_error = 'The clarification could not be saved. No notification was created.'
                response = {'evaluation_id': evaluation_id, 'state': 'COMPLETED', 'submitted_context': [asdict(e) for e in events],
                            'source': sorted({e.metadata['source'] for e in events}), 'now': request.now.isoformat(),
                            'candidates': diagnostics, 'result': result.to_dict(), 'notification_id': notification.notification_id if notification else None,
                            'delivery': delivery, 'replayed': False,
                            'check_in_id': check_in_id, 'check_in_error': check_in_error}
                # Preserve the real RunResult/TraceEvents; delivery policy is separately reported.
                with self.scope():
                    if notification:
                        repo.save_notification(notification)
                    repo.save_context_evaluation(ContextEvaluation(evaluation_id, stamp, response))
                return response
            except Exception:
                # No guessed decisions or silent sample/model fallback.
                response = {'evaluation_id': evaluation_id, 'state': 'FAILED_SAFE', 'source': sorted({e.metadata['source'] for e in events}),
                            'notification_id': None, 'delivery': 'NOT_APPROVED',
                            'error': 'Context evaluation unavailable. Check Nightshift and repository configuration; no notification was created.'}
                repo.save_context_evaluation(ContextEvaluation(evaluation_id, stamp, response))
                return response

    def _approved(self, result, events, allowed, model, stamp):
        if result.final_action.value != 'SURFACE' or result.error:
            return None, 'NOT_APPROVED'
        repo, payload = self.repository, result.message_payload or {}
        loop = repo.get_open_loop(result.loop_id)
        if not loop or loop.status not in ACTIVE or loop.loop_id not in allowed or self._blocked(loop.loop_id):
            return None, 'SUPPRESSED'
        # Require the same actual NVIDIA/Nemotron routing receipts used in the live scripts.
        traces = [t for t in result.trace_events if t.agent in {'CONTEXT', 'CRITIC', 'OPEN_LOOP'} and t.action not in {'RETRY', 'FAILED'}]
        if not model or 'nemotron' not in model.lower() or not all(t.receipt and t.receipt.get('provider') == 'nvidia' and t.receipt.get('requested_model') == model and t.receipt.get('routed_model') == model for t in traces):
            return None, 'BLOCKED_UNVERIFIED_MODEL_RECEIPT'
        if not any(t.agent == 'CRITIC' and t.action == 'SURFACE' for t in traces):
            return None, 'NOT_APPROVED'
        entities = repo.get_entities(sorted({k.entity_id for k in repo.get_loop_entities([loop.loop_id])}))
        evidence = repo.get_related_evidence([e.entity_id for e in entities], limit=10000)
        known = {e.evidence_id: e for e in evidence}
        ids, context_ids = payload.get('evidence_ids', []), payload.get('context_ids', [])
        if not ids or not context_ids or not set(ids) <= known.keys() or not set(context_ids) <= {e.context_id for e in events} or any(e.sensitive for e in evidence):
            return None, 'BLOCKED_MISSING_OR_PRIVATE_EVIDENCE'
        cited = [e for e in events if e.context_id in context_ids]
        if all(e.context_type == ContextType.LOCATION for e in cited) and not any(
                located_entity(entity, event, self.strong, self.moderate)['match'] in {'strong', 'moderate'}
                for entity in entities for event in cited):
            return None, 'BLOCKED_UNVERIFIED_PROXIMITY'
        nid = 'notice_' + result.run_id
        selected = [known[eid] for eid in ids]
        return Notification(nid, loop.loop_id, stamp, {
            'title': loop.title, 'message': 'An intention you saved may be relevant now. Revisit the evidence behind it.',
            'reason': payload['reason'], 'run_id': result.run_id, 'trigger_types': sorted({e.context_type.value for e in events if e.context_id in context_ids}),
            'sources': sorted({e.metadata['source'] for e in events if e.context_id in context_ids}),
            'context_ids': context_ids, 'entities': [{'entity_id': e.entity_id, 'name': e.name} for e in entities],
            'evidence': [{'evidence_id': e.evidence_id, 'summary': e.summary,
                          'image_url': f'/evidence/{e.evidence_id}/image' if e.image_ref else None} for e in selected],
            'delivery_status': 'APPROVED', 'read': False, 'dismissed': False, 'feedback': None,
            'snoozed_until': None, 'feedback_events': [],
        }), 'APPROVED_PENDING_DELIVERY'

    def visible(self, notification):
        loop = self.repository.get_open_loop(notification.loop_id)
        p = notification.payload
        return bool(loop and loop.status in ACTIVE and not p.get('dismissed') and p.get('feedback') not in TERMINAL_FEEDBACK
                    and not (p.get('snoozed_until') and aware(p['snoozed_until']) > self.clock()))

    def list_notifications(self):
        active = {l.loop_id for l in self.repository.get_active_open_loops(limit=10000)}
        return [asdict(n) for n in self.repository.list_notifications() if n.loop_id in active
                and not n.payload.get('dismissed') and n.payload.get('feedback') not in TERMINAL_FEEDBACK
                and not (n.payload.get('snoozed_until') and aware(n.payload['snoozed_until']) > self.clock())]

    async def action(self, notification_id, action):
        async with self.lock:
            repo = self.repository
            n = repo.get_notification(notification_id)
            if n is None:
                raise KeyError(notification_id)
            p, stamp = dict(n.payload), self.clock().isoformat()
            if action == 'DELIVERED':
                if not self.visible(n) or p['delivery_status'] == 'DELIVERED':
                    return asdict(n)
                p.update(delivery_status='DELIVERED', delivered_at=stamp)
            elif action == 'READ':
                if p['read']:
                    return asdict(n)
                p.update(read=True, read_at=stamp)
            elif action == 'DISMISS':
                p['dismissed'] = True
            else:
                # Terminal feedback is immutable; a later stale tab cannot undo it.
                if p.get('feedback') in TERMINAL_FEEDBACK:
                    if p['feedback'] == action:
                        return asdict(n)
                    raise ContextConflict('This notification already has final feedback.')
                if action == 'SNOOZE' and p.get('snoozed_until') and aware(p['snoozed_until']) > self.clock():
                    return asdict(n)
                p['feedback'] = action
                p['snoozed_until'] = (self.clock()+timedelta(seconds=self.snooze)).isoformat() if action == 'SNOOZE' else None
                p['dismissed'] = action != 'SNOOZE'
                if action == 'SNOOZE':
                    p.update(read=False, delivery_status='APPROVED')
            p['feedback_events'] = [*p.get('feedback_events', []), {'action': action, 'timestamp': stamp}]
            review = action in {'DONE', 'SNOOZE', 'NOT_RELEVANT', 'JUST_INSPIRATION'}
            if review:
                p['feedback_review'] = {'state': 'RUNNING', 'run_id': 'feedback_' + uuid.uuid4().hex[:12],
                                        'action': action, 'started_at': stamp, 'trace_events': []}
            updated = replace(n, payload=p)
            with self.scope():
                if action == 'DONE':
                    loop = repo.get_open_loop(n.loop_id)
                    if loop and loop.status in ACTIVE:
                        repo.update_open_loop(n.loop_id, status=LoopStatus.RESOLVED, updated_at=stamp)
                repo.save_notification(updated)
            if review:
                updated = await self._review_feedback(updated)
            return asdict(updated)

    async def _review_feedback(self, notification):
        """Feedback is durable before any model call. Never reinterpret a click as new Evidence.

        Same configured Open Loop Agent/Nightshift gateway, one retry and a 20s total deadline.
        A persisted RUNNING/finished review prevents duplicate clicks from repeating model calls.
        The service lock serializes notification actions; a loop snapshot guards other writers.
        """
        from backend.app.bootstrap import sample_mode, live_models
        repo = self.repository
        review = dict(notification.payload['feedback_review'])
        action = review['action']
        traces = []

        def record(agent, kind, reason, next_step='STOP', receipt=None):
            traces.append(TraceEvent(agent, kind, reason,
                [f'notification:{notification.notification_id}', f'loop:{notification.loop_id}'],
                next_step, f'loop:{notification.loop_id}', review['run_id'], self.clock().isoformat(), receipt).to_dict())

        record('FEEDBACK', 'SAVED', 'Explicit user feedback was saved before agent review.', 'OPEN_LOOP')
        state, decision, error = 'FAILED_SAFE', None, None
        try:
            loop = repo.get_open_loop(notification.loop_id)
            if sample_mode() and not live_models():
                state = 'SKIPPED'
                raise ValueError('Recorded sample mode does not call models.')
            if loop is None or (loop.status not in ACTIVE and not (action == 'DONE' and loop.status == LoopStatus.RESOLVED)):
                state = 'SKIPPED'
                raise ValueError('No eligible intention to review.')
            links = repo.get_loop_entities([loop.loop_id])
            entities = repo.get_entities(sorted({link.entity_id for link in links}))
            evidence = repo.get_related_evidence([e.entity_id for e in entities], limit=10000)
            if not evidence or any(e.sensitive for e in evidence):
                state = 'SKIPPED'
                raise ValueError('Non-sensitive supporting Evidence is required.')
            feedback = {'action': action, 'timestamp': review['started_at'],
                        'notification_id': notification.notification_id,
                        'trigger_types': notification.payload.get('trigger_types', []),
                        'context_ids': notification.payload.get('context_ids', []),
                        'reminder': {key: notification.payload.get(key) for key in ('title', 'message', 'reason')},
                        'context_events': [asdict(event) for event in repo.get_context_events()
                                           if event.context_id in notification.payload.get('context_ids', [])]}
            async with asyncio.timeout(20):
                async with self.gateway_factory() as gateway:
                    agent = build_orchestrator(gateway, repo, now=lambda: self.clock().isoformat()).open_loop_agent
                    for attempt in range(2):
                        try:
                            gateway.last_routing = {}
                            decision = await agent.review_feedback(loop, evidence, entities, feedback)
                            routing = getattr(gateway, 'last_routing', {}) or {}
                            model = gateway.reasoning_model
                            if (not model or 'nemotron' not in model.lower() or routing.get('provider') != 'nvidia'
                                    or routing.get('requested_model') != model or routing.get('routed_model') != model):
                                raise ValueError('Model routing receipt could not be verified.')
                            receipt = {key: routing.get(key) for key in ('provider', 'requested_model', 'routed_model')}
                            break
                        except Exception:
                            decision = None
                            if attempt:
                                raise
                            record('OPEN_LOOP', 'RETRY', 'Feedback review failed; retrying once.', 'OPEN_LOOP')
            # Other ingestion/check-in operations may have revised this loop while the model ran.
            with self.scope():
                if repo.get_open_loop(loop.loop_id) != loop:
                    raise ValueError('Intention changed while feedback was reviewed.')
                changes = {}
                if decision.decision == 'REVISE':
                    changes['title'] = decision.proposed_title
                if decision.decision == 'DORMANT':
                    changes['status'] = LoopStatus.DORMANT
                elif decision.decision == 'RESOLVE':
                    changes['status'] = LoopStatus.RESOLVED
                if changes:
                    repo.update_open_loop(loop.loop_id, **changes, updated_at=self.clock().isoformat())
                record('OPEN_LOOP', decision.decision, decision.concise_reason, receipt=receipt)
                state = 'COMPLETED'
                return self._save_feedback_review(notification, review, state, traces, decision)
        except asyncio.CancelledError:
            record('OPEN_LOOP', 'FAILED', 'Review interrupted; explicit feedback remains saved.')
            self._save_feedback_review(notification, review, 'FAILED_SAFE', traces)
            raise
        except Exception:
            if state != 'SKIPPED':
                state = 'FAILED_SAFE'
            error = ('Feedback saved. Agent review was unavailable or unsafe; no inferred update was applied.'
                     if state != 'SKIPPED' else 'Feedback saved. No eligible non-sensitive live agent review was available.')
            record('OPEN_LOOP', 'FAILED' if state != 'SKIPPED' else 'SKIPPED', error)
        return self._save_feedback_review(notification, review, state, traces, error=error)

    def _save_feedback_review(self, notification, review, state, traces, decision=None, error=None):
        review.update(state=state, finished_at=self.clock().isoformat(), trace_events=traces)
        if decision is not None:
            review['decision'] = asdict(decision)
        if error:
            review['error'] = error
        payload = dict(notification.payload)
        payload['feedback_review'] = review
        events = [dict(event) for event in payload['feedback_events']]
        events[-1]['agent_review'] = review
        payload['feedback_events'] = events
        updated = replace(notification, payload=payload)
        self.repository.save_notification(updated)
        return updated
