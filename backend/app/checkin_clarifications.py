"""Persist agent uncertainty and return explicit answers to the Open Loop Agent.

Uses the existing CheckIn JSON and repository; no synthetic Evidence or placeholder loop.
"""
import asyncio
from backend.app import aio
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from zoneinfo import ZoneInfo

from backend.app.bootstrap import build_orchestrator, sample_mode, live_models
from backend.app.domain.models import CheckIn, LoopStatus

KIND = 'AGENT_CLARIFICATION'
ACTIVE = {LoopStatus.OPEN, LoopStatus.ACTIVE}


def now():
    return datetime.now(timezone.utc)


def scope(repo):
    return getattr(repo, 'unit_of_work', nullcontext)()


def receipt(gateway):
    routing = getattr(gateway, 'last_routing', {}) or {}
    model = gateway.reasoning_model
    if (not model or 'nemotron' not in model.lower() or routing.get('provider') != 'nvidia'
            or routing.get('requested_model') != model or routing.get('routed_model') != model):
        raise ValueError('Unverified reasoning receipt.')
    return {key: routing[key] for key in ('provider', 'requested_model', 'routed_model')}


def grounding(repo, evidence_ids, entity_ids):
    evidence = [repo.get_evidence(eid) for eid in evidence_ids]
    entities = repo.get_entities(entity_ids)
    if not evidence or any(e is None or e.sensitive for e in evidence) or not entities:
        raise ValueError('Non-sensitive linked grounding is required.')
    links = repo.get_evidence_entities(evidence_ids)
    if not set(entity_ids) <= {link.entity_id for link in links} or set(entity_ids) != {entity.entity_id for entity in entities}:
        raise ValueError('Unlinked entities cannot ground a question.')
    return evidence, entities


def available(repo, entity_ids, stamp):
    """One outstanding question per entity set, three outstanding total, 24h after answering."""
    items = [item for item in repo.get_check_ins() if item.kind == KIND]
    items = [item for item in items if item.status != 'PENDING' or not item.loop_id
             or ((target := repo.get_open_loop(item.loop_id)) is not None and target.status in ACTIVE)]
    if sum(item.status == 'PENDING' for item in items) >= 3:
        return False
    for item in items:
        if set(item.question.get('_entity_ids', [])) != set(entity_ids):
            continue
        if item.status == 'PENDING':
            return False
        if item.answered_at and stamp - datetime.fromisoformat(item.answered_at) < timedelta(hours=24):
            return False
    return True


def queue(repo, evidence, entities, *, text, options, uncertainty, origin, loop_id=None, model_receipt=None, clock=now):
    stamp = clock()
    if not available(repo, [e.entity_id for e in entities], stamp):
        return None
    digest = hashlib.sha256((' '.join(sorted(e.entity_id for e in entities)) + '|' + uncertainty).encode()).hexdigest()[:16]
    qid = f'clarify_{stamp.strftime("%Y%m%d%H%M%S%f")}_{digest}'
    domain = evidence[0].domain
    if domain not in {'shopping', 'food', 'travel', 'destination'}:
        return None
    question = {'id': qid, 'loop_id': loop_id or '', 'type': 'CLARIFY', 'response_mode': 'options',
        'domain': 'destination' if domain == 'travel' else domain,
        'summary': evidence[0].summary, 'question': text, 'context': 'A quick clarification about what you saved.',
        'supporting_images': [], 'options': [*options,
            {'value': 'other', 'label': 'Something else', 'allows_comment': True, 'comment_required': True},
            {'value': 'not_sure', 'label': 'Not sure yet'}],
        '_evidence_ids': [e.evidence_id for e in evidence], '_entity_ids': [e.entity_id for e in entities],
        '_uncertainty': uncertainty, '_origin': origin, '_receipt': model_receipt}
    item = CheckIn(qid, stamp.astimezone(ZoneInfo('Australia/Melbourne')).date().isoformat(), KIND,
                   loop_id or '', None, question, 'PENDING', stamp.isoformat())
    repo.save_check_in(item)
    return qid


async def after_upload(agent, repo, decision, result, emit):
    """Called only when the real Open Loop decision reports material uncertainty."""
    if not decision or not decision.material_uncertainty or not result.evidence_id:
        return None
    try:
        links = repo.get_evidence_entities([result.evidence_id])
        entity_ids = sorted({link.entity_id for link in links})
        evidence, entities = grounding(repo, [result.evidence_id], entity_ids)
        if not available(repo, entity_ids, now()):
            return None
        async with aio.timeout(30):
            for attempt in range(2):
                try:
                    agent.gateway.last_routing = {}
                    generated = await agent.clarification_question(evidence, entities, decision.material_uncertainty)
                    routing = receipt(agent.gateway)
                    break
                except Exception:
                    if attempt:
                        raise
                    emit('OPEN_LOOP', 'RETRY', 'Clarification generation failed; retrying once.', next_step='OPEN_LOOP')
        with scope(repo):
            qid = queue(repo, evidence, entities, text=generated['question'], options=generated['options'],
                uncertainty=decision.material_uncertainty, origin='OPEN_LOOP', loop_id=result.loop_id, model_receipt=routing)
        if qid:
            emit('OPEN_LOOP', 'ASK', 'A material uncertainty needs the person’s answer.',
                 input_refs=[f'evidence:{result.evidence_id}'], output_ref=f'checkin:{qid}', next_step='CHECK_IN', receipt=routing)
        return qid
    except Exception:
        emit('OPEN_LOOP', 'CLARIFICATION_UNAVAILABLE', 'Saved Evidence is safe; a clarification could not be prepared.', next_step='STOP')
        return None


def after_critic(repo, result, *, clock=now):
    if result.final_action.value != 'ASK' or not result.question or not result.loop_id:
        return None
    loop = repo.get_open_loop(result.loop_id)
    if not loop or loop.status not in ACTIVE:
        return None
    links = repo.get_loop_entities([loop.loop_id])
    entity_ids = sorted({link.entity_id for link in links})
    evidence = repo.get_related_evidence(entity_ids, limit=10000)
    evidence, entities = grounding(repo, [e.evidence_id for e in evidence], entity_ids)
    trace = next((t for t in reversed(result.trace_events) if t.agent == 'CRITIC' and t.action == 'ASK'), None)
    if not trace or not trace.receipt or trace.receipt.get('provider') != 'nvidia':
        return None
    model = trace.receipt.get('requested_model')
    if not model or 'nemotron' not in model.lower() or trace.receipt.get('routed_model') != model:
        return None
    with scope(repo):
        return queue(repo, evidence, entities, text=result.question, options=[],
            uncertainty=(result.message_payload or {}).get('uncertainty') or result.question,
            origin='CRITIC', loop_id=loop.loop_id, model_receipt=trace.receipt, clock=clock)


class ClarificationConflict(ValueError):
    pass


class ClarificationService:
    def __init__(self, repo, gateway_factory, *, lock=None, clock=now):
        self.repo, self.gateway_factory, self.clock = repo, gateway_factory, clock
        self.lock = lock or asyncio.Lock()

    async def respond(self, qid, response, comment):
        async with self.lock:
            repo = self.repo
            item = repo.get_check_in(qid)
            if not item or item.kind != KIND:
                raise KeyError(qid)
            comment = (comment or '').strip() or None
            if item.status == 'ANSWERED':
                if (item.response, item.comment) != (response, comment):
                    raise ClarificationConflict('This clarification was already answered.')
                return {'ok': True, 'agent_review': item.question.get('_answer_review')}
            option = next((o for o in item.question['options'] if o['value'] == response), None)
            if not option or (option.get('comment_required') and not comment):
                raise ValueError('Choose an offered answer and add an explanation when required.')
            if comment and not option.get('allows_comment'):
                raise ValueError('This answer does not accept an explanation.')
            stamp = self.clock().isoformat()
            review = {'state': 'RUNNING', 'run_id': 'clarify_answer_' + uuid.uuid4().hex[:12], 'trace_events': []}
            question = {**item.question, '_answer_review': review}
            item = replace(item, question=question, status='ANSWERED', response=response, comment=comment, answered_at=stamp)
            repo.save_check_in(item)  # Durable user answer before a model is opened.
            def finish(state, **fields):
                current = {**review, 'state': state, 'finished_at': self.clock().isoformat(), **fields}
                repo.save_check_in(replace(item, question={**item.question, '_answer_review': current}))
                return {'ok': True, 'agent_review': current}
            if response == 'not_sure':
                return finish('DEFERRED')
            try:
                if sample_mode() and not live_models():
                    return finish('SKIPPED')
                evidence, entities = grounding(repo, item.question['_evidence_ids'], item.question['_entity_ids'])
                target = repo.get_open_loop(item.loop_id) if item.loop_id else None
                if not item.loop_id:
                    # A newer upload may have formed an intention while this question waited.
                    candidates = repo.get_active_open_loops(limit=10000)
                    wanted = {entity.entity_id for entity in entities}
                    loop_ids = {link.loop_id for link in repo.get_loop_entities([loop.loop_id for loop in candidates]) if link.entity_id in wanted}
                    matches = [loop for loop in candidates if loop.loop_id in loop_ids]
                    if len(matches) > 1:
                        raise ValueError('Several intentions now match; do not create a duplicate.')
                    target = matches[0] if matches else None
                if item.loop_id and (not target or target.status not in ACTIVE):
                    raise ValueError('The intention is no longer active.')
                async with aio.timeout(40):
                    async with self.gateway_factory() as gateway:
                        agent = build_orchestrator(gateway, repo, now=lambda: self.clock().isoformat()).open_loop_agent
                        for attempt in range(2):
                            try:
                                gateway.last_routing = {}
                                decision = await agent.decide_clarification(item, evidence, entities, target)
                                routing = receipt(gateway)
                                break
                            except Exception:
                                if attempt:
                                    raise
                                review['trace_events'].append({'agent': 'OPEN_LOOP', 'action': 'RETRY', 'reason': 'Retrying answer review once.'})
                with scope(repo):
                    if target and repo.get_open_loop(target.loop_id) != target:
                        raise ValueError('The intention changed during review.')
                    if not target:
                        active_ids = [loop.loop_id for loop in repo.get_active_open_loops(limit=10000)]
                        if any(link.entity_id in {entity.entity_id for entity in entities} for link in repo.get_loop_entities(active_ids)):
                            raise ValueError('A matching intention appeared during review.')
                    loop = agent.apply(decision)
                    review['trace_events'].append({'agent': 'OPEN_LOOP', 'action': decision.decision.value,
                        'reason': decision.concise_reason, 'receipt': routing, 'run_id': review['run_id'],
                        'input_refs': [f'checkin:{qid}'], 'output_ref': f'loop:{loop.loop_id}' if loop else None})
                    return finish('COMPLETED', decision=asdict(decision), loop_id=loop.loop_id if loop else None)
            except asyncio.CancelledError:
                finish('FAILED_SAFE', error='Answer saved; review was interrupted.')
                raise
            except Exception:
                return finish('FAILED_SAFE', error='Answer saved; no agent update could be confirmed.')
