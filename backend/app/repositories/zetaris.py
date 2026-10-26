"""Canonical LoopRepository backed by six native Zetaris Iceberg tables.

All values are JDBC parameters. Retrieval follows persisted graph edges, not
filename labels, fuzzy matching, or vectors. Application IDs are never replaced.

JDBC transactions are unavailable. A single-process unit of work serializes local
readers/writers and compensates failed writes. This is NOT a distributed/multi-
table transaction: other processes can observe intermediate state, and failed
compensation needs operator reconciliation. Run one app writer for this MVP.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
import json
import re
from threading import RLock
from typing import Sequence

from backend.app.adapters.zetaris import ZetarisError
from backend.app.domain.models import CheckIn, ContextEvent, ContextType, Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop

_FIELDS = {
    'context_evaluations': ('evaluation_id', 'created_at', 'payload_json'),
    'notifications': ('notification_id', 'loop_id', 'created_at', 'payload_json'),
    'evidence': ('evidence_id', 'source', 'domain', 'summary', 'timestamp', 'sensitive', 'confidence', 'image_ref'),
    'entities': ('entity_id', 'entity_type', 'domain', 'name', 'category', 'subcategory', 'brand', 'location_name', 'city', 'country', 'metadata_json'),
    'evidence_entities': ('evidence_id', 'entity_id', 'relationship', 'confidence'),
    'open_loops': ('loop_id', 'title', 'domain', 'status', 'confidence', 'created_at', 'updated_at'),
    'loop_entities': ('loop_id', 'entity_id', 'relationship', 'confidence'),
    'context_events': ('context_id', 'context_type', 'title', 'occurs_at', 'location_name', 'city', 'country', 'metadata_json'),
    'check_ins': ('check_in_id', 'day', 'kind', 'loop_id', 'other_loop_id', 'question_json', 'status', 'created_at', 'response', 'comment', 'answered_at'),
}
_KEYS = {'evidence': ('evidence_id',), 'entities': ('entity_id',),
         'context_evaluations': ('evaluation_id',), 'notifications': ('notification_id',),
         'evidence_entities': ('evidence_id', 'entity_id', 'relationship'), 'open_loops': ('loop_id',),
         'loop_entities': ('loop_id', 'entity_id', 'relationship'), 'context_events': ('context_id',), 'check_ins': ('check_in_id',)}


class EvidenceConflict(ZetarisError):
    pass


class IndeterminateWrite(ZetarisError):
    pass


def _ids(values: Sequence[str]) -> list[str]:
    if isinstance(values, str) or any(not isinstance(value, str) or not value for value in values):
        raise ValueError('Expected a sequence of non-empty application IDs.')
    return list(values)


def _limit(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('Limit must be a non-negative integer.')
    return str(value)


def _entity(row) -> Entity:
    return Entity(*row[:-1], metadata=json.loads(row[-1]))


def _loop(row) -> OpenLoop:
    values = list(row)
    values[3] = LoopStatus(values[3])
    return OpenLoop(*values)


class ZetarisRepository:
    def __init__(self, connection, *, namespace: str = 'recall_data.app'):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', namespace):
            raise ValueError('Namespace must be a catalog and namespace identifier.')
        self.connection = connection
        self.namespace = namespace
        self._lock = RLock()
        self._journal: list | None = None
        self._needs_reconciliation = False

    def _table(self, table: str) -> str:
        if table not in _FIELDS:
            raise ValueError('Unknown Recall table.')
        return self.namespace + '.' + table

    def _fields(self, table: str, alias: str = '') -> str:
        prefix = alias + '.' if alias else ''
        return ', '.join(prefix + '`' + field + '`' for field in _FIELDS[table])

    def _row(self, table: str, keys: Sequence) -> tuple | None:
        where = ' AND '.join('`' + key + '` = ?' for key in _KEYS[table])
        rows = self.connection.query(f'SELECT {self._fields(table)} FROM {self._table(table)} WHERE {where}', keys)
        if len(rows) > 1:
            raise ZetarisError('Duplicate application IDs found; reconcile stored data before writing.')
        return tuple(rows[0]) if rows else None

    def _merge(self, table: str, row: tuple) -> None:
        fields = _FIELDS[table]
        source = ', '.join(f'CAST(? AS {"DOUBLE" if field == "confidence" and table != "evidence" else "BOOLEAN" if field == "sensitive" else "STRING"}) AS `{field}`' for field in fields)
        on = ' AND '.join(f't.`{key}` = s.`{key}`' for key in _KEYS[table])
        updates = ', '.join(f'`{field}` = s.`{field}`' for field in fields if field not in _KEYS[table])
        columns = ', '.join(f'`{field}`' for field in fields)
        values = ', '.join(f's.`{field}`' for field in fields)
        self.connection.query(f'MERGE INTO {self._table(table)} t USING (SELECT {source}) s ON {on} '
                              f'WHEN MATCHED THEN UPDATE SET {updates} WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values})', row)

    def _change(self, table: str, row: tuple) -> None:
        if table == 'evidence':
            raise EvidenceConflict('Historical Evidence cannot be updated or deleted.')
        keys = tuple(row[_FIELDS[table].index(key)] for key in _KEYS[table])
        old = self._row(table, keys)
        if old == row:
            return
        if self._journal is None:
            raise ZetarisError('Write attempted outside the repository unit of work.')
        self._journal.append((table, keys, old))
        self._merge(table, row)

    @contextmanager
    def unit_of_work(self):
        """Compensation scope, not a JDBC transaction. Never spans model calls."""
        with self._lock:
            outer = self._journal is None
            if outer:
                if self._needs_reconciliation:
                    raise ZetarisError('Repository writes are blocked pending reconciliation of a previous uncertain or partially compensated write.')
                self._journal = []
            try:
                yield self
            except IndeterminateWrite:
                # Evidence may have committed. Never delete it or its grounding graph.
                self._needs_reconciliation = True
                raise
            except Exception:
                if outer:
                    failures = 0
                    for table, keys, old in reversed(self._journal):
                        try:
                            if old is not None:
                                self._merge(table, old)
                            else:
                                where = ' AND '.join(f'`{key}` = ?' for key in _KEYS[table])
                                self.connection.query(f'DELETE FROM {self._table(table)} WHERE {where}', keys)
                        except Exception:
                            failures += 1
                    if failures:
                        self._needs_reconciliation = True
                        raise ZetarisError('Write and compensation failed; partial state may exist. Stop writes and reconcile the affected graph.') from None
                raise
            finally:
                if outer:
                    self._journal = None

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        with self._lock:
            row = self._row('evidence', [evidence_id])
            return Evidence(*row) if row else None

    def list_evidence(self) -> list[Evidence]:
        """Read-only helper in stable order (timestamp, then ID); the agent protocol remains unchanged."""
        with self._lock:
            rows = self.connection.query(f'SELECT {self._fields("evidence")} FROM {self._table("evidence")} ORDER BY timestamp, evidence_id')
            return [Evidence(*row) for row in rows]

    def get_evidence_entities(self, evidence_ids: Sequence[str]) -> list[EvidenceEntity]:
        """Read actual persisted edges for storage verification and provenance."""
        with self._lock:
            ids = _ids(evidence_ids)
            if not ids:
                return []
            rows = self.connection.query(f'SELECT {self._fields("evidence_entities")} FROM {self._table("evidence_entities")} WHERE evidence_id IN ({", ".join("?" for _ in ids)}) ORDER BY evidence_id, entity_id, relationship', ids)
            return [EvidenceEntity(*row) for row in rows]

    def save_entity(self, entity: Entity) -> None:
        values = asdict(entity)
        values['metadata_json'] = json.dumps(values.pop('metadata'), sort_keys=True, separators=(',', ':'))
        with self.unit_of_work():
            self._change('entities', tuple(values[field] for field in _FIELDS['entities']))

    def save_evidence(self, evidence: Evidence, entities: Sequence[Entity], links: Sequence[EvidenceEntity]) -> None:
        with self.unit_of_work():
            entity_map = {entity.entity_id: entity for entity in entities}
            if len(entity_map) != len(entities):
                raise ValueError('Duplicate entity IDs in evidence graph.')
            if any(link.evidence_id != evidence.evidence_id for link in links):
                raise ValueError('Evidence link refers to a different evidence ID.')
            link_keys = {}
            for link in links:
                key = (link.evidence_id, link.entity_id, link.relationship)
                if key in link_keys and link_keys[key] != link:
                    raise ValueError('Conflicting duplicate evidence links.')
                link_keys[key] = link
            linked_ids = {link.entity_id for link in links}
            known = set(entity_map) | {entity.entity_id for entity in self.get_entities(sorted(linked_ids - set(entity_map)))}
            if not linked_ids <= known:
                raise ValueError('Evidence link refers to a missing entity.')
            current = self.get_evidence(evidence.evidence_id)
            expected_links = set(links)
            if current is not None:
                existing_links = self.connection.query(f'SELECT {self._fields("evidence_entities")} FROM {self._table("evidence_entities")} WHERE evidence_id = ?', [evidence.evidence_id])
                if current != evidence or {EvidenceEntity(*row) for row in existing_links} != expected_links:
                    raise EvidenceConflict('Existing Evidence or its historical links differ; original records were preserved.')
                return
            for entity in entities:
                self.save_entity(entity)
            for link in sorted(expected_links, key=lambda item: (item.entity_id, item.relationship)):
                self._change('evidence_entities', tuple(asdict(link).values()))
            columns = self._fields('evidence')
            placeholders = ', '.join('?' for _ in _FIELDS['evidence'])
            try:
                # Last write publishes the evidence graph. Evidence is never merged/deleted.
                self.connection.query(f'INSERT INTO {self._table("evidence")} ({columns}) VALUES ({placeholders})', tuple(asdict(evidence).values()))
            except ZetarisError as error:
                try:
                    stored = self.get_evidence(evidence.evidence_id)
                except Exception:
                    raise IndeterminateWrite('Evidence write outcome is unknown. Graph retained; reconcile before retrying.') from None
                if stored == evidence:
                    return
                if stored is not None:
                    raise IndeterminateWrite('Evidence ID conflict after write. Graph retained for reconciliation.') from None
                raise error

    def get_related_evidence(self, entity_ids: Sequence[str], *, domain: str | None = None,
                             exclude_evidence_ids: Sequence[str] = (), limit: int = 10) -> list[Evidence]:
        with self._lock:
            ids, excluded, limit_sql = _ids(entity_ids), _ids(exclude_evidence_ids), _limit(limit)
            if not ids or limit == 0:
                return []
            sql = f'SELECT DISTINCT {self._fields("evidence", "e")} FROM {self._table("evidence")} e JOIN {self._table("evidence_entities")} l ON e.evidence_id = l.evidence_id WHERE l.entity_id IN ({", ".join("?" for _ in ids)})'
            args = list(ids)
            if domain is not None:
                sql += ' AND e.domain = ?'
                args.append(domain)
            if excluded:
                sql += f' AND e.evidence_id NOT IN ({", ".join("?" for _ in excluded)})'
                args.extend(excluded)
            rows = self.connection.query(sql + f' ORDER BY e.timestamp DESC LIMIT {limit_sql}', args)
            return [Evidence(*row) for row in rows]

    def get_related_entities(self, entity_ids: Sequence[str], *, domain: str | None = None, limit: int = 20) -> list[Entity]:
        with self._lock:
            ids, limit_sql = _ids(entity_ids), _limit(limit)
            if not ids or limit == 0:
                return []
            placeholders = ', '.join('?' for _ in ids)
            sql = f'SELECT DISTINCT {self._fields("entities", "e")} FROM {self._table("entities")} e JOIN {self._table("evidence_entities")} a ON e.entity_id = a.entity_id JOIN {self._table("evidence_entities")} b ON a.evidence_id = b.evidence_id JOIN {self._table("evidence")} v ON v.evidence_id = a.evidence_id WHERE b.entity_id IN ({placeholders}) AND e.entity_id NOT IN ({placeholders})'
            args = ids + ids
            if domain is not None:
                sql += ' AND e.domain = ?'
                args.append(domain)
            return [_entity(row) for row in self.connection.query(sql + f' ORDER BY e.entity_id LIMIT {limit_sql}', args)]

    def get_candidate_open_loops(self, entity_ids: Sequence[str], *, domain: str | None = None, limit: int = 5) -> list[OpenLoop]:
        with self._lock:
            ids, limit_sql = _ids(entity_ids), _limit(limit)
            if limit == 0 or (not ids and domain is None):
                return []
            terms, args = [], []
            if ids:
                terms.append(f'l.loop_id IN (SELECT loop_id FROM {self._table("loop_entities")} WHERE entity_id IN ({", ".join("?" for _ in ids)}))')
                args.extend(ids)
            if domain is not None:
                terms.append('l.domain = ?')
                args.append(domain)
            sql = f'SELECT {self._fields("open_loops", "l")} FROM {self._table("open_loops")} l WHERE l.status <> ? AND ({" OR ".join(terms)}) ORDER BY l.updated_at DESC LIMIT {limit_sql}'
            return [_loop(row) for row in self.connection.query(sql, [LoopStatus.INVALIDATED.value, *args])]

    def get_active_open_loops(self, *, limit: int = 10) -> list[OpenLoop]:
        with self._lock:
            limit_sql = _limit(limit)
            sql = f'SELECT {self._fields("open_loops")} FROM {self._table("open_loops")} WHERE status IN (?, ?) ORDER BY updated_at DESC LIMIT {limit_sql}'
            return [_loop(row) for row in self.connection.query(sql, [LoopStatus.OPEN.value, LoopStatus.ACTIVE.value])]

    def get_open_loop(self, loop_id: str) -> OpenLoop | None:
        with self._lock:
            row = self._row('open_loops', [loop_id])
            return _loop(row) if row else None

    def get_entities(self, entity_ids: Sequence[str]) -> list[Entity]:
        with self._lock:
            ids = _ids(entity_ids)
            if not ids:
                return []
            rows = self.connection.query(f'SELECT {self._fields("entities")} FROM {self._table("entities")} WHERE entity_id IN ({", ".join("?" for _ in ids)})', ids)
            by_id = {row[0]: _entity(row) for row in rows}
            return [by_id[eid] for eid in ids if eid in by_id]

    def list_entities(self, *, domain: str | None = None) -> list[Entity]:
        """Read-only API projection helper; the agent protocol remains unchanged."""
        with self._lock:
            sql = f'SELECT {self._fields("entities")} FROM {self._table("entities")}'
            args = []
            if domain is not None:
                sql += ' WHERE domain = ?'
                args.append(domain)
            return [_entity(row) for row in self.connection.query(sql + ' ORDER BY entity_id', args)]

    def get_loop_entities(self, loop_ids: Sequence[str]) -> list[LoopEntity]:
        with self._lock:
            ids = _ids(loop_ids)
            if not ids:
                return []
            rows = self.connection.query(f'SELECT {self._fields("loop_entities")} FROM {self._table("loop_entities")} WHERE loop_id IN ({", ".join("?" for _ in ids)}) ORDER BY loop_id, entity_id, relationship', ids)
            return [LoopEntity(*row) for row in rows]

    def save_open_loop(self, loop: OpenLoop) -> OpenLoop:
        with self.unit_of_work():
            values = asdict(loop)
            values['status'] = loop.status.value
            self._change('open_loops', tuple(values[field] for field in _FIELDS['open_loops']))
        return loop

    def update_open_loop(self, loop_id: str, *, title: str | None = None, domain: str | None = None,
                         status: LoopStatus | None = None, confidence: float | None = None,
                         updated_at: str | None = None) -> OpenLoop:
        with self.unit_of_work():
            current = self.get_open_loop(loop_id)
            if current is None:
                raise KeyError(loop_id)
            changes = {key: value for key, value in dict(title=title, domain=domain, status=status,
                       confidence=confidence, updated_at=updated_at).items() if value is not None}
            return self.save_open_loop(replace(current, **changes))

    def link_loop_entity(self, link: LoopEntity) -> None:
        with self.unit_of_work():
            if self.get_open_loop(link.loop_id) is None or not self.get_entities([link.entity_id]):
                raise ValueError('Loop link requires an existing loop and entity.')
            key = (link.loop_id, link.entity_id, link.relationship)
            # Match the in-memory implementation's first-link-wins idempotency.
            if self._row('loop_entities', key) is None:
                self._change('loop_entities', tuple(asdict(link).values()))

    def save_context_event(self, event: ContextEvent) -> None:
        values = asdict(event)
        values['context_type'] = event.context_type.value
        values['metadata_json'] = json.dumps(values.pop('metadata'), sort_keys=True, separators=(',', ':'))
        with self.unit_of_work():
            self._change('context_events', tuple(values[field] for field in _FIELDS['context_events']))

    def get_context_events(self) -> list[ContextEvent]:
        with self._lock:
            rows = self.connection.query(f'SELECT {self._fields("context_events")} FROM {self._table("context_events")} ORDER BY context_id')
            return [ContextEvent(row[0], ContextType(row[1]), *row[2:-1], metadata=json.loads(row[-1])) for row in rows]

    def save_check_in(self, check_in: CheckIn) -> None:
        values = asdict(check_in)
        values['question_json'] = json.dumps(values.pop('question'), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        with self.unit_of_work():
            self._change('check_ins', tuple(values[field] for field in _FIELDS['check_ins']))

    @staticmethod
    def _check_in(row) -> CheckIn:
        check_in_id, day, kind, loop_id, other, question_json, status, created_at, response, comment, answered_at = row
        return CheckIn(check_in_id, day, kind, loop_id, other, json.loads(question_json), status, created_at, response, comment, answered_at)

    def get_check_in(self, check_in_id: str) -> CheckIn | None:
        with self._lock:
            row = self._row('check_ins', [check_in_id])
            return self._check_in(row) if row else None

    def get_check_ins(self, *, day: str | None = None, status: str | None = None) -> list[CheckIn]:
        with self._lock:
            clauses, args = [], []
            for column, value in (('day', day), ('status', status)):
                if value is not None:
                    clauses.append(f'`{column}` = ?')
                    args.append(value)
            where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
            rows = self.connection.query(f'SELECT {self._fields("check_ins")} FROM {self._table("check_ins")}{where} ORDER BY created_at, check_in_id', args)
            return [self._check_in(row) for row in rows]

    def save_context_evaluation(self, evaluation) -> None:
        with self.unit_of_work():
            self._change('context_evaluations', (evaluation.evaluation_id, evaluation.created_at,
                         json.dumps(evaluation.payload, sort_keys=True, separators=(',', ':'))))

    def get_context_evaluation(self, evaluation_id):
        from backend.app.repositories.context_store import ContextEvaluation
        with self._lock:
            row = self._row('context_evaluations', [evaluation_id])
            return ContextEvaluation(row[0], row[1], json.loads(row[2])) if row else None

    def save_notification(self, notification) -> None:
        with self.unit_of_work():
            self._change('notifications', (notification.notification_id, notification.loop_id, notification.created_at,
                         json.dumps(notification.payload, sort_keys=True, separators=(',', ':'))))

    def get_notification(self, notification_id):
        from backend.app.repositories.context_store import Notification
        with self._lock:
            row = self._row('notifications', [notification_id])
            return Notification(row[0], row[1], row[2], json.loads(row[3])) if row else None

    def list_notifications(self):
        from backend.app.repositories.context_store import Notification
        with self._lock:
            rows = self.connection.query(f'SELECT {self._fields("notifications")} FROM {self._table("notifications")} ORDER BY created_at DESC')
            return [Notification(row[0], row[1], row[2], json.loads(row[3])) for row in rows]
