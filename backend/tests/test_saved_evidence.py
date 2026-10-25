"""Offline checks for the actual three-key batch export and storage-only importer."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.app.agents.evidence import parse_evidence
from backend.app.ingestion.saved_evidence import SavedEvidenceError, read_saved_evidence, stored_graph, verify_stored_graph
from backend.app.repositories.zetaris import ZetarisRepository
from backend.scripts.import_evidence import import_one
from backend.tests.test_zetaris_repository import SqlHarness


class SavedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'IMG_0001.PNG').write_bytes(b'synthetic offline image fixture')
        self.path = self.root / 'IMG_0001.json'
        extraction = parse_evidence(json.dumps({'domain': 'food', 'summary': 'Synthetic unit-test café.',
                    'entities': [{'name': 'Sample café', 'type': 'place', 'location': {'location_name': 'Sample area', 'city': 'Melbourne', 'country': 'Australia'}}],
                    'sensitive': False, 'confidence': 'high'}))
        self.document = {'source_file': 'IMG_0001.PNG', 'extraction': asdict(extraction),
                         'receipt': {'requested_model': 'gpt-4o-mini', 'routed_model': 'gpt-4o-mini', 'provider': 'openai'}}
        self.write()
        self.sql = SqlHarness()
        self.addCleanup(self.sql.db.close)
        self.repo = ZetarisRepository(self.sql)

    def write(self):
        self.path.write_text(json.dumps(self.document))

    def load(self):
        return read_saved_evidence(self.path, self.root)

    def test_maps_canonical_fields_without_changing_input(self):
        before = self.path.read_bytes()
        artifact = self.load()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(artifact.artifact_sha256, hashlib.sha256(before).hexdigest())
        entity = artifact.graph.entities[0]
        self.assertEqual((entity.entity_type, entity.city, entity.location_name), ('place', 'Melbourne', 'Sample area'))
        self.assertEqual(artifact.graph.evidence.source, 'screenshot')
        self.assertEqual(artifact.graph.evidence.image_ref, 'IMG_0001.PNG')
        self.assertFalse(hasattr(artifact.graph.evidence, 'possible_intent'))

    def test_ids_are_stable_across_format_and_mtime_changes(self):
        first = self.load()
        self.path.write_text(json.dumps(self.document, indent=4))
        os.utime(self.path, (1000000000, 1000000000))
        second = self.load()
        self.assertEqual(first.graph.evidence.evidence_id, second.graph.evidence.evidence_id)
        self.assertEqual(first.graph.entities, second.graph.entities)
        self.assertNotEqual(first.graph.evidence.timestamp, second.graph.evidence.timestamp)

    def test_semantically_changed_extraction_has_new_evidence_identity(self):
        before = self.load()
        self.document['extraction']['summary'] = 'Another synthetic observation.'
        self.write()
        self.assertNotEqual(before.graph.evidence.evidence_id, self.load().graph.evidence.evidence_id)

    def test_store_and_readback_use_real_graph_and_stable_ids(self):
        artifact = self.load()
        graph, counts = import_one(self.repo, artifact)
        self.assertEqual(counts, {'inserted': 1, 'skipped': 0, 'failed': 0, 'inserted_entities': 1, 'updated_entities': 0})
        verify_stored_graph(self.repo, graph, exact_entities=True)
        self.assertEqual(self.repo.get_evidence_entities([graph.evidence.evidence_id]), graph.links)

    def test_replay_reuses_stored_timestamp_and_does_not_duplicate(self):
        first_graph, _ = import_one(self.repo, self.load())
        os.utime(self.path, (1000000000, 1000000000))
        replay_graph, counts = import_one(self.repo, self.load())
        self.assertEqual(first_graph, replay_graph)
        self.assertEqual((counts['inserted'], counts['skipped'], counts['inserted_entities']), (0, 1, 0))
        self.assertEqual(len(self.repo.get_related_evidence([first_graph.entities[0].entity_id])), 1)

    def test_entity_upsert_does_not_rewrite_historical_evidence(self):
        first, _ = import_one(self.repo, self.load())
        self.document['extraction']['summary'] = 'New synthetic observation.'
        self.document['extraction']['entities'][0]['category'] = 'cafe'
        self.write()
        second, counts = import_one(self.repo, self.load())
        self.assertEqual(counts['updated_entities'], 1)
        self.assertEqual(first.entities[0].entity_id, second.entities[0].entity_id)
        self.assertEqual(self.repo.get_evidence(first.evidence.evidence_id), first.evidence)
        verify_stored_graph(self.repo, first)

    def test_no_model_call_is_needed_to_load_or_persist(self):
        with patch('backend.app.adapters.nightshift.ModelGateway.complete', side_effect=AssertionError('Model call forbidden')):
            import_one(self.repo, self.load())

    def test_rejects_wrong_receipt_without_logging_value(self):
        self.document['receipt']['provider'] = 'private-test-value'
        self.write()
        with self.assertRaises(SavedEvidenceError) as error:
            self.load()
        self.assertNotIn('private-test-value', str(error.exception))

    def test_rejects_missing_or_unsafe_image_reference(self):
        for name in ('../IMG_0001.PNG', 'missing.PNG'):
            self.document['source_file'] = name
            self.write()
            with self.assertRaises(SavedEvidenceError):
                self.load()

    def test_does_not_drop_old_intent_field_or_silently_normalize(self):
        self.document['extraction']['possible_intent'] = 'A synthetic invalid field'
        self.write()
        with self.assertRaises(SavedEvidenceError):
            self.load()

    def test_rejects_unknown_envelope(self):
        self.document['unexpected'] = True
        self.write()
        with self.assertRaises(SavedEvidenceError):
            self.load()
