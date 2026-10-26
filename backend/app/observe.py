"""Observability around the unchanged agents and orchestrator, at the composition boundary.

Three thin wrappers let a run emit structured events WHILE it executes, so a UI can show progress and a judge can see what each step used and
decided:

  ObservedGateway     the model gateway; announces each model call (vision or reasoning) and its sanitized receipt
  ObservedRepository  the repository; sees the Evidence being stored and exactly what the Open Loop Agent reads from it
  UploadObserver      ties both to a RunRecorder, and captures the Open Loop decision by wrapping `agent.decide` on the instance

Nothing here changes what an agent decides or what the orchestrator does. Only structured inputs, retrievals, decisions, confidences, ids, receipts
and state changes are exposed; the model's reasoning is never requested, kept or shown. An observer can never break a run: every hook swallows its
own errors.
"""
from __future__ import annotations

from dataclasses import asdict
from functools import wraps
import logging

from backend.app.runs import RunRecorder

log = logging.getLogger('recall.observe')
RECEIPT_KEYS = ('requested_model', 'routed_model', 'provider')
SNIPPET = 200


def safe(method):
    """Observation must never alter or fail a run."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception('observer hook %s failed; the run is unaffected', method.__name__)
            return None
    return wrapper


def sanitize_receipt(routing: dict | None) -> dict | None:
    routing = dict(routing or {})
    return {k: routing.get(k) for k in RECEIPT_KEYS} if routing else None


def _has_image(messages) -> bool:
    return any(isinstance(m.get('content'), list) and any(isinstance(p, dict) and p.get('type') == 'image_url' for p in m['content'])
               for m in messages if isinstance(m, dict))


class ObservedGateway:
    def __init__(self, inner, observer: 'UploadObserver'):
        self._inner, self._observer = inner, observer

    @property
    def last_routing(self):
        return self._inner.last_routing

    @last_routing.setter
    def last_routing(self, value):
        self._inner.last_routing = value

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def complete(self, messages, **kwargs):
        kind = 'vision' if _has_image(messages) else 'reasoning'
        self._observer.model_started(kind, kwargs.get('model') or getattr(self._inner, 'model', None))
        try:
            content = await self._inner.complete(messages, **kwargs)
        except Exception:
            self._observer.model_finished(kind, None)
            raise
        self._observer.model_finished(kind, getattr(self._inner, 'last_routing', None))
        return content


class ObservedRepository:
    """Forwards every call unchanged. The reads the Open Loop Agent makes are reported to the observer, as are the Evidence store and loop writes."""
    _READS = ('get_related_evidence', 'get_related_entities', 'get_candidate_open_loops', 'get_loop_entities', 'get_entities')

    def __init__(self, inner, observer: 'UploadObserver'):
        self._inner, self._observer = inner, observer

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if name in self._READS:
            def read(*args, **kwargs):
                result = attribute(*args, **kwargs)
                self._observer.read(name, result)
                return result
            return read
        return attribute

    def save_evidence(self, evidence, entities, links):
        existing = {e.entity_id for e in self._inner.get_entities([e.entity_id for e in entities])} if entities else set()
        outcome = self._inner.save_evidence(evidence, entities, links)
        self._observer.stored(evidence, entities, links, existing)
        return outcome


def loop_state(repository, loop_id: str | None, *, exclude_evidence_id: str | None = None) -> dict | None:
    """A loop as the UI counts it: how many non-sensitive screenshots currently support it. Reads the real repository, not the observed one."""
    loop = repository.get_open_loop(loop_id) if loop_id else None
    if loop is None:
        return None
    entity_ids = sorted({k.entity_id for k in repository.get_loop_entities([loop_id])})
    evidence = repository.get_related_evidence(entity_ids, limit=1000) if entity_ids else []
    shown = [e for e in evidence if not e.sensitive and e.image_ref and e.evidence_id != exclude_evidence_id]
    return {'loop_id': loop.loop_id, 'title': loop.title, 'domain': loop.domain, 'status': loop.status.value, 'confidence': loop.confidence,
            'screenshots': len(shown)}


class UploadObserver:
    def __init__(self, recorder: RunRecorder, repository, *, image_ref: str):
        self.recorder, self.repository, self.image_ref = recorder, repository, image_ref
        self.zetaris = type(repository).__name__ == 'ZetarisRepository'
        self.store_agent = 'ZETARIS' if self.zetaris else 'REPOSITORY'
        self.store_label = 'Zetaris' if self.zetaris else 'the demo workspace (in-memory)'
        self.receipts: dict[str, dict | None] = {}
        self.evidence_id: str | None = None
        self.sensitive = False
        self.capturing = False
        self._reset_retrieval()
        self.decision = None
        self.before: dict | None = None
        self.memory_hits: dict[str, dict] = {}
        self.memory_added: list[str] = []

    # ---- retrieval capture ---------------------------------------------------------------------------------
    def _reset_retrieval(self) -> None:
        self.related_evidence: dict[str, dict] = {}
        self.related_entities: dict[str, str] = {}
        self.candidates: list[dict] = []
        self.loop_links: dict[str, list[str]] = {}
        self.entity_names: dict[str, str] = {}
        self.hidden_evidence = 0

    @safe
    def read(self, name: str, result) -> None:
        if not self.capturing:
            return
        if name == 'get_related_evidence':
            for item in result:
                if item.sensitive:
                    self.hidden_evidence += 1  # counted, never described
                else:
                    self.related_evidence[item.evidence_id] = {'evidence_id': item.evidence_id, 'domain': item.domain,
                                                               'summary': item.summary[:SNIPPET], 'has_image': bool(item.image_ref)}
        elif name == 'get_related_entities':
            for entity in result:
                self.related_entities[entity.entity_id] = entity.name
        elif name == 'get_candidate_open_loops':
            self.candidates = [{'loop_id': l.loop_id, 'title': l.title, 'status': l.status.value, 'confidence': l.confidence} for l in result]
        elif name == 'get_loop_entities':
            for link in result:
                self.loop_links.setdefault(link.loop_id, []).append(link.entity_id)
        elif name == 'get_entities':
            for entity in result:
                self.entity_names[entity.entity_id] = entity.name

    def _retrieval_detail(self) -> dict:
        candidates = [{**c, 'entities': [self.entity_names[i] for i in self.loop_links.get(c['loop_id'], []) if i in self.entity_names]}
                      for c in self.candidates]
        related = [{**item, 'via': 'entities+h-mem' if item['evidence_id'] in self.memory_hits else 'entities'} for item in self.related_evidence.values()]
        for evidence_id in self.memory_added:
            hit = self.memory_hits.get(evidence_id)
            if hit and evidence_id not in self.related_evidence:
                related.append({'evidence_id': evidence_id, 'domain': None, 'summary': hit['content'][:SNIPPET], 'has_image': None,
                                'via': 'h-mem', 'relevance': hit['relevance']})
        return {'related_evidence': related, 'memory_added': len(self.memory_added), 'related_entities': [{'entity_id': k, 'name': v} for k, v in self.related_entities.items()],
                'candidate_loops': candidates, 'sensitive_evidence_withheld': self.hidden_evidence}

    # ---- H-MEM (memory engine) ----------------------------------------------------------------------------
    @safe
    def memory_event(self, kind: str, payload: dict) -> None:
        refs = [f'evidence:{self.evidence_id}'] if self.evidence_id else []
        if kind == 'query':
            self.memory_hits = {h['evidence_id']: h for h in payload['hits']}
            self.recorder.emit('H-MEM', 'QUERY', f"Asked H-MEM what it remembers about this screenshot: {len(payload['hits'])} related "
                               f"{'memory' if len(payload['hits']) == 1 else 'memories'} above the {payload['threshold']} threshold.",
                               input_refs=refs, next_step='H-MEM', detail=payload)
        elif kind == 'stored':
            self.recorder.emit('H-MEM', 'STORE', f"Remembered this screenshot as {payload['layer']} memory {payload['memory_id']} "
                               f"(confidence {payload['confidence']}, with provenance and a ledger entry).", input_refs=refs, next_step='OPEN_LOOP',
                               output_ref=f"memory:{payload['memory_id']}", detail=payload)
        elif kind == 'merged':
            self.memory_added = list(payload['evidence_ids'])
        elif kind == 'unavailable':
            self.recorder.emit('H-MEM', 'UNAVAILABLE', 'H-MEM could not be reached; retrieval used shared entities only.', input_refs=refs,
                               next_step='OPEN_LOOP', detail=payload)

    # ---- model calls ---------------------------------------------------------------------------------------
    @safe
    def model_started(self, kind: str, model) -> None:
        refs = [f'image:{self.image_ref}']
        if kind == 'vision':
            self.recorder.emit('EVIDENCE', 'STARTED', 'Reading the screenshot with the vision model.', input_refs=refs, next_step='EVIDENCE',
                               detail={'model': model})
            return
        if self.capturing:  # the Open Loop Agent has read what it needs and is about to ask the model
            detail = self._retrieval_detail()
            self.capturing = False
            self.recorder.emit('OPEN_LOOP', 'RETRIEVE',
                               f"Gathered {len(detail['related_evidence'])} related Evidence records ({detail['memory_added']} found only through H-MEM), "
                               f"{len(detail['related_entities'])} related entities "
                               f"and {len(detail['candidate_loops'])} candidate loops from {self.store_label}.",
                               input_refs=[f'evidence:{self.evidence_id}'], next_step='OPEN_LOOP', detail=detail)
            self.recorder.emit('OPEN_LOOP', 'DECIDING', 'Open Loop Agent is deciding what this means for the saved intentions.',
                               input_refs=[f'evidence:{self.evidence_id}'], next_step='OPEN_LOOP',
                               detail={'model': model, 'related_evidence': len(detail['related_evidence']), 'candidate_loops': len(detail['candidate_loops'])})

    @safe
    def model_finished(self, kind: str, routing) -> None:
        self.receipts[kind] = sanitize_receipt(routing)

    # ---- storing -------------------------------------------------------------------------------------------
    @safe
    def stored(self, evidence, entities, links, existing_entity_ids: set) -> None:
        self.evidence_id, self.sensitive = evidence.evidence_id, evidence.sensitive
        refs = [f'image:{self.image_ref}']
        if evidence.sensitive:
            self.recorder.emit('EVIDENCE', 'EXTRACT', 'Screenshot flagged as sensitive; its content is withheld.', input_refs=refs, next_step=self.store_agent,
                               receipt=self.receipts.get('vision'), detail={'sensitive': True})
        else:
            self.recorder.emit('EVIDENCE', 'EXTRACT', f'Understood the screenshot: {evidence.domain}, {len(entities)} entities, confidence {evidence.confidence}.',
                               input_refs=refs, next_step=self.store_agent, receipt=self.receipts.get('vision'),
                               detail={'domain': evidence.domain, 'summary': evidence.summary, 'confidence': evidence.confidence, 'sensitive': False,
                                       'entities': [{'entity_id': e.entity_id, 'name': e.name, 'type': e.entity_type, 'category': e.category,
                                                     'subcategory': e.subcategory, 'brand': e.brand, 'location_name': e.location_name, 'city': e.city,
                                                     'country': e.country, 'attributes': dict(e.metadata)} for e in entities]})
        matched = [e for e in entities if e.entity_id in existing_entity_ids]
        new = [e for e in entities if e.entity_id not in existing_entity_ids]
        detail = {'evidence_id': evidence.evidence_id, 'entities_new': len(new), 'entities_matched_existing': len(matched), 'links': len(links),
                  'backend': 'zetaris' if self.zetaris else 'in-memory demo workspace'}
        if not evidence.sensitive:
            detail['new_entities'] = [e.name for e in new]
            detail['matched_entities'] = [e.name for e in matched]
        self.recorder.emit(self.store_agent, 'STORE', f'Stored the Evidence with {len(new)} new and {len(matched)} already-known entities in {self.store_label}.',
                           input_refs=refs, next_step='OPEN_LOOP', output_ref=f'evidence:{evidence.evidence_id}', detail=detail)
        self._reset_retrieval()
        self.capturing = True

    # ---- the decision --------------------------------------------------------------------------------------
    def wrap_decide(self, agent) -> None:
        """Capture the Open Loop Agent's structured decision. The agent's own method still runs, unchanged."""
        original = agent.decide
        observer = self

        async def decide(*args, **kwargs):
            decision = await original(*args, **kwargs)
            observer.decided(decision)
            return decision

        agent.decide = decide

    @safe
    def decided(self, decision) -> None:
        self.capturing = False  # a sensitive screenshot is decided locally: nothing was retrieved
        self.decision = decision
        if decision.target_loop_id:
            self.before = loop_state(self.repository, decision.target_loop_id, exclude_evidence_id=self.evidence_id)
        detail = {'decision': decision.decision.value, 'target_loop_id': decision.target_loop_id, 'proposed_title': decision.proposed_title,
                  'domain': decision.domain, 'confidence': decision.confidence, 'supporting_evidence_ids': list(decision.supporting_evidence_ids),
                  'supporting_entity_ids': list(decision.supporting_entity_ids), 'material_uncertainty': decision.material_uncertainty}
        self.recorder.emit('OPEN_LOOP', decision.decision.value, decision.concise_reason, input_refs=[f'evidence:{self.evidence_id}'],
                           next_step='STATE', output_ref=f'loop:{decision.target_loop_id}' if decision.target_loop_id else None,
                           receipt=self.receipts.get('reasoning'), detail=detail)

    # ---- the outcome ---------------------------------------------------------------------------------------
    @safe
    def outcome(self, result) -> dict | None:
        """Before/after state of the loop this screenshot touched. Returns the state change for the response."""
        after = loop_state(self.repository, result.loop_id)
        if self.decision is None or after is None:
            return None
        if self.decision.decision.value == 'CREATE':
            change, before = 'created', None
        else:
            before = self.before
            parts = []
            if before and before['screenshots'] != after['screenshots']:
                parts.append(f"supporting screenshots {before['screenshots']} → {after['screenshots']}")
            if before and before['title'] != after['title']:
                parts.append('title revised')
            if before and before['status'] != after['status']:
                parts.append(f"status {before['status']} → {after['status']}")
            change = ', '.join(parts) or 'updated'
        detail = {'change': change, 'before': before, 'after': after}
        self.recorder.emit('OPEN_LOOP', 'STATE', f"Loop \"{after['title']}\": {change}.", input_refs=[f'loop:{after["loop_id"]}'], next_step='STOP',
                           output_ref=f'loop:{after["loop_id"]}', detail=detail)
        return detail
