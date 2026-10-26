"""Loop consolidation: find look-alike Open Loops, merge exact duplicates, ask the person about the rest.

The Critic only judges (MERGE / ASK / KEEP_SEPARATE). This module is not an agent and makes no model decisions: it picks candidate
pairs deterministically, applies a merge through the repository, and files an ASK as a Check-in question for the day. A person's
answer, not a model, settles every ASK. Nothing here edits or deletes Evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Sequence

from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.agents.critic import CriticAgent, CriticError, DuplicateDecision, DuplicateKind
from backend.app.domain import models as m
from backend.app.domain.trace import TraceEvent

MAX_PAIRS_PER_CALL = 8
MIN_SHARED_TOKENS = 1
MAX_ATTEMPTS = 2  # one call plus at most one retry, as in the orchestrator
_STOPWORDS = {'the', 'and', 'for', 'from', 'with', 'interested', 'ordered', 'collection', 'this', 'that', 'sneakers', 'shoes', 'burger',
              'restaurant', 'melbourne', 'australia', 'men', 'mens', 'women', 'womens', 'new', 'best', 'cbd', 'north', 'south', 'east', 'west',
              'city', 'square', 'late', 'night', 'cafe', 'bar', 'free', 'entry', 'under', 'hour', 'hamburger', 'halal'}


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r'[a-z0-9]+', text.casefold()) if len(t) >= 3 and t not in _STOPWORDS}


def pair_key(a: str, b: str) -> str:
    return '|'.join(sorted((a, b)))


def candidate_pairs(loops: Sequence[m.OpenLoop], entities_by_loop: dict[str, list[m.Entity]]) -> list[tuple[str, str]]:
    """Cheap and deterministic: same domain and either a shared entity or a shared distinctive name token (generic words are ignored). Over-selecting
    only costs a model call that answers KEEP_SEPARATE once; under-selecting would hide a real duplicate."""
    words = {l.loop_id: tokens(l.title) | {t for e in entities_by_loop.get(l.loop_id, []) for t in tokens(e.name)} for l in loops}
    ents = {l.loop_id: {e.entity_id for e in entities_by_loop.get(l.loop_id, [])} for l in loops}
    pairs = []
    for i, a in enumerate(loops):
        for b in loops[i + 1:]:
            if a.domain != b.domain:
                continue
            if ents[a.loop_id] & ents[b.loop_id] or len(words[a.loop_id] & words[b.loop_id]) >= MIN_SHARED_TOKENS:
                pairs.append((a.loop_id, b.loop_id))
    return pairs


def check_in_id(day: str, a: str, b: str) -> str:
    return 'ci_' + hashlib.sha256(f'{day}|{pair_key(a, b)}'.encode()).hexdigest()[:14]


def short(title: str) -> str:
    return re.sub(r'^Interested in\s+', '', title)


def merge_question(day: str, keep: m.OpenLoop, fold: m.OpenLoop, text: str) -> dict:
    """CheckInQuestion payload (frontend contract). Supporting images are attached when the question is served."""
    return {
        'id': check_in_id(day, keep.loop_id, fold.loop_id), 'loop_id': keep.loop_id, 'type': 'CONFIRM',
        'domain': 'destination' if keep.domain == 'travel' else keep.domain,
        'summary': f'You saved "{short(keep.title)}" and "{short(fold.title)}".',
        'question': text,
        'context': 'Recall wants to know whether these are one thing or two. If they are the same thing they are combined; otherwise both stay.',
        'supporting_images': [],
        'positive': {'value': 'same', 'label': 'Yes, same thing'},
        'negative': {'value': 'different', 'label': 'No, keep both'},
        'options': [{'value': 'related', 'label': 'Related, keep both'}, {'value': 'other', 'label': 'Something else', 'allows_comment': True}],
    }


def apply_merge(repository, keep_id: str, fold_id: str, now: str) -> None:
    """Fold one loop into another. The folded loop is INVALIDATED (hidden, not deleted); its entities move to the kept loop."""
    if keep_id == fold_id:
        raise ValueError('Cannot merge a loop into itself.')
    keep, fold = repository.get_open_loop(keep_id), repository.get_open_loop(fold_id)
    if keep is None or fold is None:
        raise ValueError('Both loops must exist to merge them.')
    from contextlib import nullcontext
    scope = getattr(repository, 'unit_of_work', nullcontext)
    with scope():
        for link in repository.get_loop_entities([fold_id]):
            repository.link_loop_entity(m.LoopEntity(keep_id, link.entity_id, link.relationship, link.confidence))
        repository.update_open_loop(fold_id, status=m.LoopStatus.INVALIDATED, updated_at=now)
        repository.update_open_loop(keep_id, updated_at=now)


@dataclass
class ConsolidationResult:
    run_id: str
    day: str
    candidate_pairs: int = 0
    judged: int = 0
    merged: list[tuple[str, str]] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    kept_separate: int = 0
    model_calls: int = 0
    errors: list[str] = field(default_factory=list)
    trace_events: list[TraceEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {'run_id': self.run_id, 'day': self.day, 'candidate_pairs': self.candidate_pairs, 'judged': self.judged,
                'merged': self.merged, 'asked': self.asked, 'kept_separate': self.kept_separate, 'model_calls': self.model_calls,
                'errors': self.errors, 'trace_events': [e.to_dict() for e in self.trace_events]}


class Consolidator:
    def __init__(self, critic: CriticAgent, repository, *, judged_path: Path, now: Callable[[], str] | None = None):
        self.critic, self.repository, self.judged_path = critic, repository, judged_path
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat(timespec='seconds'))

    def _judged(self) -> dict:
        return json.loads(self.judged_path.read_text()) if self.judged_path.is_file() else {}

    def _save_judged(self, value: dict) -> None:
        self.judged_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.judged_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True))
        temporary.replace(self.judged_path)

    def plan(self, day: str) -> tuple[list[m.OpenLoop], dict, list[tuple[str, str]]]:
        """Read-only: loops, their entities, and the pairs still worth judging today."""
        loops = self.repository.get_active_open_loops(limit=1000)
        links = self.repository.get_loop_entities([l.loop_id for l in loops])
        entities = {e.entity_id: e for e in self.repository.get_entities(sorted({k.entity_id for k in links}))}
        by_loop = {l.loop_id: [entities[k.entity_id] for k in links if k.loop_id == l.loop_id and k.entity_id in entities] for l in loops}
        judged = self._judged()
        settled = {pair_key(c.loop_id, c.other_loop_id) for c in self.repository.get_check_ins() if c.other_loop_id
                   and (c.status == 'ANSWERED' or (c.status == 'PENDING' and c.day == day))}
        pairs = [p for p in candidate_pairs(loops, by_loop) if pair_key(*p) not in judged and pair_key(*p) not in settled]
        return loops, by_loop, pairs

    async def run(self, day: str, run_id: str, *, dry_run: bool = False) -> ConsolidationResult:
        result = ConsolidationResult(run_id, day)
        trace = lambda agent, action, reason, refs=(), next_step=None, output=None, receipt=None: result.trace_events.append(  # noqa: E731
            TraceEvent(agent, action, reason, list(refs), next_step, output, run_id, self._now(), receipt))
        loops, by_loop, pairs = self.plan(day)
        result.candidate_pairs = len(pairs)
        trace('ZETARIS', 'LOAD', f'Loaded {len(loops)} active Open Loops from Zetaris; {len(pairs)} look-alike pairs need a decision.',
              [f'loop:{l.loop_id}' for l in loops], 'CRITIC')
        if dry_run or not pairs:
            return result
        by_id = {l.loop_id: l for l in loops}
        evidence = {}
        for loop in loops:
            if any(loop.loop_id in p for p in pairs):
                ents = by_loop[loop.loop_id]
                found = self.repository.get_related_evidence([e.entity_id for e in ents], limit=3) if ents else []
                evidence[loop.loop_id] = [e.summary for e in found if not e.sensitive]
        views = [{'loop_id': l.loop_id, 'title': l.title, 'domain': l.domain, 'entities': [e.name for e in by_loop[l.loop_id]],
                  'evidence': evidence.get(l.loop_id, [])} for l in loops]
        judged = self._judged()
        for start in range(0, len(pairs), MAX_PAIRS_PER_CALL):
            chunk = pairs[start:start + MAX_PAIRS_PER_CALL]
            decisions, receipt, error = None, None, None
            for attempt in range(MAX_ATTEMPTS):
                self.critic.gateway.last_routing = {}
                try:
                    result.model_calls += 1
                    decisions = await self.critic.review_duplicates(views, chunk)
                    routing = dict(getattr(self.critic.gateway, 'last_routing', None) or {})
                    receipt = {k: routing.get(k) for k in ('requested_model', 'routed_model', 'provider')} if routing else None
                    break
                except (CriticError, ModelGatewayError) as exc:
                    error = str(exc)
                    trace('CRITIC', 'RETRY' if attempt == 0 else 'FAILED', f'Duplicate review failed ({error}).',
                          [f'loop:{i}' for p in chunk for i in p], 'CRITIC' if attempt == 0 else 'STOP')
            if decisions is None:
                result.errors.append(error or 'failed')  # nothing was merged or asked; the pairs are retried tomorrow
                continue
            for d in decisions:
                self._apply(d, by_id, day, result, judged, trace, receipt)
            self._save_judged(judged)
        return result

    def _apply(self, d: DuplicateDecision, by_id, day, result, judged, trace, receipt) -> None:
        a, b = (by_id[i] for i in d.loop_ids)
        refs = [f'loop:{a.loop_id}', f'loop:{b.loop_id}']
        live = [self.repository.get_open_loop(i) for i in d.loop_ids]
        if any(l is None or l.status not in (m.LoopStatus.OPEN, m.LoopStatus.ACTIVE) for l in live):
            trace('CRITIC', 'SKIPPED', 'One of the loops is no longer active (for example merged earlier in this run).', refs, 'STOP')
            return
        result.judged += 1
        if d.decision == DuplicateKind.MERGE:
            keep = by_id[d.canonical_loop_id]
            fold = b if keep is a else a
            try:
                apply_merge(self.repository, keep.loop_id, fold.loop_id, self._now())
            except Exception as exc:  # noqa: BLE001 - a failed write must not look like a merge
                result.errors.append(f'Merge failed: {type(exc).__name__}')
                trace('CRITIC', 'MERGE_FAILED', 'The duplicate could not be merged; nothing was changed by the decision.', refs, 'STOP')
                return
            result.merged.append((keep.loop_id, fold.loop_id))
            trace('CRITIC', 'MERGE', d.concise_reason, refs, 'STOP', f'loop:{keep.loop_id}', receipt)
        elif d.decision == DuplicateKind.ASK:
            keep = a if a.updated_at >= b.updated_at else b
            fold = b if keep is a else a
            question = merge_question(day, keep, fold, d.question or 'Are these the same thing?')
            self.repository.save_check_in(m.CheckIn(question['id'], day, 'MERGE_LOOPS', keep.loop_id, fold.loop_id, question, 'PENDING', self._now()))
            result.asked.append(question['id'])
            trace('CRITIC', 'ASK', d.concise_reason, refs, 'CHECK_IN', f'checkin:{question["id"]}', receipt)
        else:
            result.kept_separate += 1
            judged[pair_key(a.loop_id, b.loop_id)] = {'decision': 'KEEP_SEPARATE', 'at': self._now()}
            trace('CRITIC', 'KEEP_SEPARATE', d.concise_reason, refs, 'STOP', None, receipt)
