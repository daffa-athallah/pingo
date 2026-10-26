"""Recall's use of the Meterless H-MEM engine (engines/hmem, the unmodified reference implementation, served by engines/hmem/server.ts).

What it is for: the Open Loop Agent finds related Evidence only through shared entity IDs, so a screenshot of "Elmo's Hamburger" never
reached three earlier screenshots of "Elmo's Hamburger Restaurant". H-MEM is Recall's governed memory of what each saved screenshot showed. It
ranks by meaning, keywords, tags, domain and entities with a per-record confidence, and it keeps provenance and an audit ledger. The wrapper
here adds H-MEM's hits to the related-Evidence list the agent already receives. Agent logic is unchanged.

Rules this module keeps:
  * sensitive Evidence is never written to memory (nothing about it is stored, queried or described);
  * memory only helps retrieval. The ids it returns are resolved against the real repository, and ones that do not exist are dropped;
  * H-MEM being down never breaks a run: retrieval falls back to entity links alone and the run records that.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Callable, Sequence
import urllib.error
import urllib.request

CONFIDENCE = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
TOP_N = 5
THRESHOLD = 0.35  # H-MEM's own default, applied to the final score (after the confidence multiplier)
EVIDENCE_REF = 'evidence:'


class HMemError(RuntimeError):
    pass


class HMemClient:
    def __init__(self, base_url: str, *, timeout: float = 5.0):
        self.base_url, self.timeout = base_url.rstrip('/'), timeout

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read() or b'null')
        except urllib.error.HTTPError as exc:
            raise HMemError(f'H-MEM returned HTTP {exc.code}.') from None
        except (urllib.error.URLError, OSError, ValueError):
            raise HMemError('H-MEM is not reachable.') from None

    def health(self) -> dict | None:
        try:
            return self._call('GET', '/health', timeout=1.5)
        except HMemError:
            return None

    def add(self, memory: dict) -> dict:
        return self._call('POST', '/memories', memory)

    def query(self, text: str, *, top_n: int = TOP_N, threshold: float = THRESHOLD) -> dict:
        return self._call('POST', '/query', {'query': text, 'topN': top_n, 'threshold': threshold})

    def refs(self) -> set[str]:
        return set(self._call('GET', '/refs').get('refs', []))

    def ledger(self, limit: int = 50, memory_id: str | None = None) -> dict:
        return self._call('GET', f'/ledger?limit={int(limit)}' + (f'&memoryId={memory_id}' if memory_id else ''))

    def feedback(self, memory_id: str, kind: str) -> None:
        self._call('POST', '/feedback', {'memoryId': memory_id, 'kind': kind})

    def reset(self) -> None:
        self._call('POST', '/reset', {})


def _epoch_ms(timestamp: str) -> int:
    try:
        return int(datetime.fromisoformat(timestamp).timestamp() * 1000)
    except ValueError:
        return 0


def memory_text(evidence, entities: Sequence) -> str:
    """What is remembered and what is searched for: what the screenshot showed, and the names it contained."""
    names = ', '.join(dict.fromkeys(e.name for e in entities))
    return f'{evidence.summary} Entities: {names}.' if names else evidence.summary


def memory_from_evidence(evidence, entities: Sequence, *, layer: str = 'working') -> dict | None:
    """The H-MEM record for one screenshot's Evidence. Sensitive Evidence is never remembered."""
    if evidence.sensitive:
        return None
    return {
        'content': memory_text(evidence, entities), 'type': 'factual', 'layer': layer,
        'confidence': CONFIDENCE.get(evidence.confidence, 0.6), 'source': f'screenshot:{evidence.image_ref or evidence.evidence_id}',
        'tags': [evidence.domain], 'goalRunId': None,
        'provenance': {'origin': 'file_save', 'learnedAt': _epoch_ms(evidence.timestamp), 'label': 'Saved screenshot',
                       'refs': [EVIDENCE_REF + evidence.evidence_id]},
    }


def evidence_id_of(memory: dict) -> str | None:
    for ref in (memory.get('provenance') or {}).get('refs', []):
        if ref.startswith(EVIDENCE_REF):
            return ref[len(EVIDENCE_REF):]
    return None


def seed_from_repository(client: HMemClient, repository) -> dict:
    """Remember the Evidence already stored (idempotent: references already in memory are skipped). Returns counts."""
    present = client.refs()
    evidence = repository.list_evidence()
    links = repository.get_evidence_entities([e.evidence_id for e in evidence])
    names = {e.entity_id: e for e in repository.list_entities()}
    added = skipped = 0
    for item in evidence:
        if EVIDENCE_REF + item.evidence_id in present:
            skipped += 1
            continue
        entities = [names[k.entity_id] for k in links if k.evidence_id == item.evidence_id and k.entity_id in names]
        record = memory_from_evidence(item, entities, layer='long_term')  # established history
        if record is None:
            continue
        client.add(record)
        added += 1
    return {'added': added, 'already_present': skipped}


class HMemRepository:
    """Repository proxy for one ingestion run. Everything passes through unchanged except two things:
    after Evidence is stored it queries H-MEM with what the screenshot showed and then remembers it, and get_related_evidence adds the
    Evidence behind H-MEM's hits to the entity-linked results. `listener(kind, payload)` receives structured events for the run trace."""

    def __init__(self, inner, client: HMemClient, *, listener: Callable[[str, dict], None] | None = None):
        self._inner, self._client, self._listener = inner, client, listener or (lambda kind, payload: None)
        self.available = True
        self.hits: list[dict] = []
        self.query_text: str | None = None
        self.memory_id: str | None = None

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _emit(self, kind: str, payload: dict) -> None:
        try:
            self._listener(kind, payload)
        except Exception:  # noqa: BLE001 - observing never affects retrieval
            pass

    def save_evidence(self, evidence, entities, links):
        outcome = self._inner.save_evidence(evidence, entities, links)
        if evidence.sensitive:
            return outcome  # not queried, not remembered, not described
        self.query_text = memory_text(evidence, entities)
        try:
            result = self._client.query(self.query_text)  # before remembering this screenshot, so it cannot find itself
            hits = []
            for item in result.get('memories', []):
                ref = evidence_id_of(item)
                if ref and ref != evidence.evidence_id and self._inner.get_evidence(ref) is not None:
                    hits.append({'memory_id': item['id'], 'evidence_id': ref, 'relevance': round(item['relevance'], 4), 'layer': item['layer'],
                                 'confidence': item['confidence'], 'content': item['content'][:200], 'entities': item.get('entities', []),
                                 'provenance': item.get('provenance', {}).get('label')})
            self.hits = hits
            self._emit('query', {'query': self.query_text, 'hits': hits, 'trace': result.get('trace', {}), 'threshold': THRESHOLD, 'top_n': TOP_N})
        except HMemError as exc:
            self.available, self.hits = False, []
            self._emit('unavailable', {'reason': str(exc)})
            return outcome
        try:
            stored = self._client.add(memory_from_evidence(evidence, entities))
            self.memory_id = stored['id']
            self._emit('stored', {'memory_id': stored['id'], 'layer': stored['layer'], 'confidence': stored['confidence'], 'source': stored['source'],
                                  'provenance': stored['provenance'], 'domain': stored['domain'], 'entities': stored['entities']})
        except HMemError as exc:
            self._emit('unavailable', {'reason': str(exc)})
        return outcome

    def get_related_evidence(self, entity_ids, *, domain=None, exclude_evidence_ids=(), limit=10):
        base = list(self._inner.get_related_evidence(entity_ids, domain=domain, exclude_evidence_ids=exclude_evidence_ids, limit=limit))
        seen = {e.evidence_id for e in base} | set(exclude_evidence_ids)
        added = []
        for hit in self.hits:
            if len(base) >= limit:
                break
            if hit['evidence_id'] in seen:
                continue
            item = self._inner.get_evidence(hit['evidence_id'])
            if item is None or item.sensitive or (domain is not None and item.domain != domain):
                continue
            seen.add(item.evidence_id)
            base.append(item)
            added.append(item.evidence_id)
        if self.hits:
            # Which Evidence reached the agent only because of memory: reported in the run trace.
            self._emit('merged', {'evidence_ids': added, 'already_linked': [h['evidence_id'] for h in self.hits if h['evidence_id'] not in added]})
        return base

    def memory_evidence_ids(self) -> set[str]:
        return {h['evidence_id'] for h in self.hits}
