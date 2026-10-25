"""Offline repository behavior with a SQLite SQL harness, NOT a live Zetaris claim.

SELECT/JOIN/filter/order queries run in a real local SQL engine. Only the native
Iceberg MERGE syntax is translated to SQLite UPSERT for failure injection. Live
Iceberg DML is verified separately and never required by this test module.
"""
from dataclasses import replace
import re
import sqlite3
import unittest

from backend.app.adapters.zetaris import ZetarisError
from backend.app.domain.models import ContextEvent, ContextType, Entity, Evidence, EvidenceEntity, LoopEntity, LoopStatus, OpenLoop
from backend.app.repositories.zetaris import EvidenceConflict, IndeterminateWrite, ZetarisRepository


class SqlHarness:
    def __init__(self):
        self.db = sqlite3.connect(':memory:', isolation_level=None, check_same_thread=False)
        self.db.executescript('''
          CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, source TEXT, domain TEXT, summary TEXT, timestamp TEXT, sensitive BOOLEAN, confidence TEXT, image_ref TEXT);
          CREATE TABLE entities (entity_id TEXT PRIMARY KEY, entity_type TEXT, domain TEXT, name TEXT, category TEXT, subcategory TEXT, brand TEXT, location_name TEXT, city TEXT, country TEXT, metadata_json TEXT);
          CREATE TABLE evidence_entities (evidence_id TEXT, entity_id TEXT, relationship TEXT, confidence REAL, PRIMARY KEY(evidence_id,entity_id,relationship));
          CREATE TABLE open_loops (loop_id TEXT PRIMARY KEY, title TEXT, domain TEXT, status TEXT, confidence REAL, created_at TEXT, updated_at TEXT);
          CREATE TABLE loop_entities (loop_id TEXT, entity_id TEXT, relationship TEXT, confidence REAL, PRIMARY KEY(loop_id,entity_id,relationship));
          CREATE TABLE context_events (context_id TEXT PRIMARY KEY, context_type TEXT, title TEXT, occurs_at TEXT, location_name TEXT, city TEXT, country TEXT, metadata_json TEXT);
        ''')
        self.failures = []
        self.calls = []
        self.after_insert = None

    def query(self, sql, parameters=()):
        self.calls.append((sql, tuple(parameters)))
        if self.failures and self.failures[0](sql):
            self.failures.pop(0)
            raise ZetarisError('Injected offline storage failure')
        statement = sql.replace('recall_data.app.', '')
        merge = re.match(r'MERGE INTO (\w+) t ', statement)
        if merge:
            table = merge.group(1)
            fields = re.findall(r' AS `([^`]+)`', statement)
            keys = {row[1] for row in self.db.execute(f'PRAGMA table_info({table})') if row[5]}
            updates = ', '.join(f'`{field}`=excluded.`{field}`' for field in fields if field not in keys)
            statement = f'INSERT INTO {table} ({", ".join(fields)}) VALUES ({", ".join("?" for _ in fields)}) ON CONFLICT DO UPDATE SET {updates}'
        cursor = self.db.execute(statement, tuple(parameters))
        rows = cursor.fetchall() if cursor.description else []
        if sql.startswith('INSERT INTO recall_data.app.evidence') and self.after_insert:
            self.after_insert()
        return rows


def evidence(id='ev_1', **changes):
    item = Evidence(id, 'offline_test_fixture', 'food', 'Synthetic café evidence.', '2026-10-25T10:00:00+00:00', False, 'high', 'IMG_0001.PNG')
    return replace(item, **changes)


def entity(id='ent_1', **changes):
    return replace(Entity(id, 'place', 'food', 'Sample café', city='Melbourne', metadata={'test': 'fixture'}), **changes)


def loop(id='loop_1', **changes):
    return replace(OpenLoop(id, 'Possibly interested in a café', 'food', LoopStatus.OPEN, 0.6,
                            '2026-10-25T10:00:00+00:00', '2026-10-25T10:00:00+00:00'), **changes)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.sql = SqlHarness()
        self.addCleanup(self.sql.db.close)
        self.repo = ZetarisRepository(self.sql)

    def save(self, ev=None, entities=None):
        ev = ev or evidence()
        entities = entities or [entity()]
        links = [EvidenceEntity(ev.evidence_id, item.entity_id, 'depicted', 0.9) for item in entities]
        self.repo.save_evidence(ev, entities, links)
        return ev, entities, links

    def test_evidence_and_entity_round_trip_preserves_ids_and_fields(self):
        ev, entities, _ = self.save()
        self.assertEqual(self.repo.get_evidence(ev.evidence_id), ev)
        self.assertEqual(self.repo.get_entities(['ent_1']), entities)
        self.assertFalse(hasattr(self.repo.get_evidence(ev.evidence_id), 'possible_intent'))

    def test_entity_upsert_for_second_evidence_keeps_identity(self):
        self.save()
        changed = entity(category='cafe', metadata={'price': 'sample'})
        self.save(evidence('ev_2'), [changed])
        self.assertEqual(self.repo.get_entities(['ent_1']), [changed])
        self.assertEqual(len(self.repo.get_related_evidence(['ent_1'])), 2)

    def test_related_evidence_uses_edges_exclusions_domain_order_and_limit(self):
        self.save()
        newer = evidence('ev_2', timestamp='2026-10-26T10:00:00+00:00')
        self.save(newer)
        self.assertEqual(self.repo.get_related_evidence(['ent_1'], limit=1), [newer])
        self.assertEqual(self.repo.get_related_evidence(['ent_1'], exclude_evidence_ids=['ev_2']), [evidence()])
        self.assertEqual(self.repo.get_related_evidence(['ent_1'], domain='shopping'), [])
        self.assertEqual(self.repo.get_related_evidence(['missing']), [])

    def test_related_entities_share_real_evidence_and_exclude_query_entities(self):
        second = entity('ent_2', name='Another sample café')
        self.save(entities=[entity(), second])
        self.assertEqual(self.repo.get_related_entities(['ent_1']), [second])
        self.assertEqual(self.repo.get_related_entities(['ent_1'], domain='shopping'), [])
        self.assertEqual(self.repo.get_related_entities(['unknown']), [])

    def test_filename_does_not_create_semantic_relationships(self):
        self.save(evidence(image_ref='shopping_tokyo_jacket.PNG'))
        self.assertEqual(self.repo.get_related_evidence(['ent_1'])[0].domain, 'food')
        self.assertEqual(self.repo.get_related_evidence(['shopping_tokyo_jacket']), [])

    def test_duplicate_graph_import_is_idempotent(self):
        ev, entities, links = self.save()
        writes = lambda: sum(sql.startswith(('MERGE', 'INSERT', 'DELETE')) for sql, _ in self.sql.calls)
        before = writes()
        self.repo.save_evidence(ev, entities, links + links)
        self.assertEqual(writes(), before)
        self.assertEqual(len(self.repo.get_related_evidence(['ent_1'])), 1)

    def test_changed_evidence_is_rejected_without_mutation(self):
        self.save()
        with self.assertRaises(EvidenceConflict):
            self.save(evidence(summary='An incompatible rewrite.'))
        self.assertEqual(self.repo.get_evidence('ev_1'), evidence())

    def test_changed_historical_links_are_rejected(self):
        self.save()
        with self.assertRaises(EvidenceConflict):
            self.repo.save_evidence(evidence(), [entity()], [])
        self.assertEqual(self.repo.get_related_evidence(['ent_1']), [evidence()])

    def test_invalid_links_fail_before_any_write(self):
        for link in (EvidenceEntity('wrong_ev', 'ent_1', 'depicted', 0.9), EvidenceEntity('ev_1', 'missing', 'depicted', 0.9)):
            with self.assertRaises(ValueError):
                self.repo.save_evidence(evidence(), [entity()], [link])
        self.assertEqual(self.repo.get_entities(['ent_1']), [])

    def test_conflicting_duplicate_links_fail_before_mutation(self):
        links = [EvidenceEntity('ev_1', 'ent_1', 'depicted', value) for value in (0.3, 0.9)]
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            self.repo.save_evidence(evidence(), [entity()], links)
        self.assertIsNone(self.repo.get_evidence('ev_1'))
        self.assertEqual(self.repo.get_entities(['ent_1']), [])

    def test_open_loop_round_trip_and_missing_lookup(self):
        self.assertEqual(self.repo.save_open_loop(loop()), loop())
        self.assertEqual(self.repo.get_open_loop('loop_1'), loop())
        self.assertIsNone(self.repo.get_open_loop('missing'))

    def test_loop_entity_link_requires_existing_records(self):
        with self.assertRaises(ValueError):
            self.repo.link_loop_entity(LoopEntity('missing', 'missing', 'subject', 0.5))
        self.assertEqual(self.repo.get_loop_entities(['missing']), [])

    def test_loop_links_are_idempotent_and_filter_requested_loops(self):
        self.save()
        self.repo.save_open_loop(loop())
        link = LoopEntity('loop_1', 'ent_1', 'subject', 0.5)
        self.repo.link_loop_entity(link)
        self.repo.link_loop_entity(replace(link, confidence=0.9))
        self.assertEqual(self.repo.get_loop_entities(['loop_1']), [link])
        self.assertEqual(self.repo.get_loop_entities(['unrelated']), [])

    def test_candidate_loops_match_domain_fallback_and_status_rules(self):
        self.save()
        self.repo.save_open_loop(loop())
        self.repo.save_open_loop(loop('loop_other', domain='shopping'))
        self.repo.link_loop_entity(LoopEntity('loop_other', 'ent_1', 'subject', 0.8))
        self.repo.save_open_loop(loop('invalid', status=LoopStatus.INVALIDATED))
        self.repo.save_open_loop(loop('resolved', status=LoopStatus.RESOLVED))
        self.assertEqual({item.loop_id for item in self.repo.get_candidate_open_loops(['ent_1'], domain='food')}, {'loop_1', 'loop_other', 'resolved'})
        self.assertEqual([item.loop_id for item in self.repo.get_candidate_open_loops(['ent_1'])], ['loop_other'])

    def test_active_loops_are_open_or_active_ordered_and_limited(self):
        self.repo.save_open_loop(loop())
        newest = loop('loop_2', status=LoopStatus.ACTIVE, updated_at='2026-10-26T10:00:00+00:00')
        self.repo.save_open_loop(newest)
        self.repo.save_open_loop(loop('resolved', status=LoopStatus.RESOLVED))
        self.assertEqual(self.repo.get_active_open_loops(limit=1), [newest])

    def test_get_entities_preserves_requested_order_and_missing_behavior(self):
        first, second = entity(), entity('ent_2')
        self.save(entities=[first, second])
        self.assertEqual(self.repo.get_entities(['ent_2', 'missing', 'ent_1', 'ent_2']), [second, first, second])

    def test_update_loop_preserves_evidence_and_handles_zero_confidence(self):
        self.save()
        self.repo.save_open_loop(loop())
        changed = self.repo.update_open_loop('loop_1', title='Revised hypothesis', confidence=0.0, status=LoopStatus.DORMANT)
        self.assertEqual((changed.title, changed.confidence, changed.status), ('Revised hypothesis', 0.0, LoopStatus.DORMANT))
        self.assertEqual(self.repo.get_evidence('ev_1'), evidence())
        with self.assertRaises(KeyError):
            self.repo.update_open_loop('missing', title='x')

    def test_failed_evidence_write_restores_entity_metadata_and_removes_staged_links(self):
        original = entity()
        self.repo.save_entity(original)
        self.sql.failures = [lambda sql: sql.startswith('INSERT INTO recall_data.app.evidence')]
        with self.assertRaises(ZetarisError):
            self.save(entities=[replace(original, metadata={'changed': 'sample'}), entity('ent_new')])
        self.assertEqual(self.repo.get_entities(['ent_1', 'ent_new']), [original])
        self.assertIsNone(self.repo.get_evidence('ev_1'))
        self.assertEqual(self.repo.get_related_entities(['ent_1']), [])

    def test_unit_of_work_removes_orphan_loop_after_link_failure(self):
        self.save()
        self.sql.failures = [lambda sql: sql.startswith('MERGE INTO recall_data.app.loop_entities')]
        with self.assertRaises(ZetarisError):
            with self.repo.unit_of_work():
                self.repo.save_open_loop(loop())
                self.repo.link_loop_entity(LoopEntity('loop_1', 'ent_1', 'subject', 0.5))
        self.assertIsNone(self.repo.get_open_loop('loop_1'))
        self.assertEqual(self.repo.get_loop_entities(['loop_1']), [])
        self.assertEqual(self.repo.get_evidence('ev_1'), evidence())

    def test_failed_loop_revision_restores_old_loop(self):
        self.save()
        self.repo.save_open_loop(loop())
        with self.assertRaises(ValueError):
            with self.repo.unit_of_work():
                self.repo.update_open_loop('loop_1', title='Changed')
                self.repo.link_loop_entity(LoopEntity('loop_1', 'missing', 'subject', 0.5))
        self.assertEqual(self.repo.get_open_loop('loop_1'), loop())

    def test_compensation_failure_is_reported_explicitly(self):
        self.sql.failures = [lambda sql: sql.startswith('INSERT INTO recall_data.app.evidence'),
                             lambda sql: sql.startswith('DELETE FROM recall_data.app.evidence_entities')]
        with self.assertRaisesRegex(ZetarisError, 'partial state may exist'):
            self.save()
        with self.assertRaisesRegex(ZetarisError, 'blocked pending reconciliation'):
            self.repo.save_entity(entity('another'))

    def test_acknowledgement_lost_after_evidence_commit_is_reconciled(self):
        def lost_response():
            self.sql.after_insert = None
            raise ZetarisError('Injected lost acknowledgement')
        self.sql.after_insert = lost_response
        self.save()
        self.assertEqual(self.repo.get_evidence('ev_1'), evidence())
        self.assertEqual(self.repo.get_related_evidence(['ent_1']), [evidence()])

    def test_unknown_commit_keeps_graph_and_reports_indeterminate_state(self):
        def lost_response():
            self.sql.after_insert = None
            self.sql.failures = [lambda sql: sql.startswith('SELECT') and 'FROM recall_data.app.evidence WHERE' in sql]
            raise ZetarisError('Injected lost acknowledgement')
        self.sql.after_insert = lost_response
        with self.assertRaises(IndeterminateWrite):
            self.save()
        self.assertEqual(self.repo.get_evidence('ev_1'), evidence())
        self.assertEqual(self.repo.get_entities(['ent_1']), [entity()])
        with self.assertRaisesRegex(ZetarisError, 'blocked pending reconciliation'):
            self.repo.save_open_loop(loop())

    def test_empty_inputs_zero_limits_and_invalid_limits(self):
        self.assertEqual(self.repo.get_entities([]), [])
        self.assertEqual(self.repo.get_loop_entities([]), [])
        self.assertEqual(self.repo.get_related_evidence([], limit=0), [])
        self.assertEqual(self.repo.get_related_entities([], limit=0), [])
        self.assertEqual(self.repo.get_candidate_open_loops([]), [])
        with self.assertRaises(ValueError):
            self.repo.get_active_open_loops(limit=-1)

    def test_context_event_round_trip(self):
        item = ContextEvent('ctx_test', ContextType.TIME, 'Synthetic test time', metadata={'sample': 'yes'})
        self.repo.save_context_event(item)
        self.assertEqual(self.repo.get_context_events(), [item])


if __name__ == '__main__':
    unittest.main()
