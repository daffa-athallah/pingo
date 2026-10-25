"""Prepared JSON conversion and repeat-perception protection, using labeled fixtures."""
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.agents.evidence import EvidenceError, parse_evidence
from backend.app.ingestion.prepared import PreparedDataError, load_prepared
from backend.scripts.recall_data import batch, extract


class PreparedTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'IMG_0001.PNG'
        self.image.write_bytes(b'unit-test image placeholder; not a real screenshot')
        self.file = self.root / 'IMG_0001.json'
        self.raw = json.dumps({'domain': 'food', 'summary': 'Synthetic unit-test café fixture.',
            'entities': [{'name': 'Sample café', 'type': 'place', 'location': {'location_name': 'Sample café', 'city': 'Melbourne', 'country': None}}],
            'sensitive': False, 'confidence': 'high'})
        self.document = {'schema_version': 1, 'evidence_id': 'ev_unit_fixture', 'source': 'screenshot',
                         'image_ref': self.image.name, 'image_sha256': hashlib.sha256(self.image.read_bytes()).hexdigest(),
                         'timestamp': '2026-10-25T00:00:00+00:00', 'raw_response': self.raw,
                         'extraction': asdict(parse_evidence(self.raw)), 'receipt': {}}
        self.write()

    def write(self):
        self.file.write_text(json.dumps(self.document))

    def test_conversion_preserves_original_id_timestamp_and_raw_json(self):
        before = self.file.read_bytes()
        result = load_prepared(self.file, self.root)
        self.assertEqual(result.graph.evidence.evidence_id, 'ev_unit_fixture')
        self.assertEqual(result.graph.evidence.timestamp, self.document['timestamp'])
        self.assertEqual(result.document['raw_response'], self.raw)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertIsNone(result.graph.entities[0].location_name)
        self.assertNotIn('possible_intent', asdict(result.graph.evidence))

    def test_repeat_conversion_preserves_graph_and_identity(self):
        self.assertEqual(load_prepared(self.file, self.root), load_prepared(self.file, self.root))

    def test_changed_structure_is_not_silently_repaired(self):
        self.document['extraction']['domain'] = 'shopping'
        self.write()
        with self.assertRaisesRegex(PreparedDataError, 'differs'):
            load_prepared(self.file, self.root)

    def test_rejects_changed_image_bytes(self):
        self.image.write_bytes(b'changed')
        with self.assertRaisesRegex(PreparedDataError, 'bytes'):
            load_prepared(self.file, self.root)

    def test_rejects_path_traversal(self):
        self.document['image_ref'] = '../IMG_0001.PNG'
        self.write()
        with self.assertRaisesRegex(PreparedDataError, 'basename'):
            load_prepared(self.file, self.root)

    def test_rejects_unversioned_old_model_json(self):
        self.file.write_text(self.raw)
        with self.assertRaisesRegex(PreparedDataError, 'Unsupported'):
            load_prepared(self.file, self.root)

    def test_possible_intent_is_rejected_not_dropped(self):
        self.document['raw_response'] = json.dumps({**json.loads(self.raw), 'possible_intent': 'Invented intention'})
        self.write()
        with self.assertRaises(EvidenceError):
            load_prepared(self.file, self.root)

    def test_timestamp_requires_timezone(self):
        self.document['timestamp'] = '2026-10-25T00:00:00'
        self.write()
        with self.assertRaisesRegex(PreparedDataError, 'timezone'):
            load_prepared(self.file, self.root)

    def test_existing_valid_artifact_never_calls_gateway(self):
        args = SimpleNamespace(output=self.file, image=self.image)
        with patch('backend.scripts.recall_data.ModelGateway.from_env') as gateway:
            asyncio.run(extract(args))
        gateway.assert_not_called()

    def test_existing_artifact_for_different_image_does_not_trigger_perception(self):
        other = self.root / 'IMG_0002.PNG'
        other.write_bytes(b'another unit-test placeholder')
        with patch('backend.scripts.recall_data.ModelGateway.from_env') as gateway:
            with self.assertRaisesRegex(PreparedDataError, 'different screenshot'):
                asyncio.run(extract(SimpleNamespace(output=self.file, image=other)))
        gateway.assert_not_called()

    def test_batch_dry_run_does_not_open_storage_or_call_models(self):
        args = SimpleNamespace(input=self.file, images=self.root, dry_run=True)
        with patch('backend.scripts.recall_data.open_repository') as storage, patch('backend.scripts.recall_data.ModelGateway.from_env') as gateway:
            batch(args)
        storage.assert_not_called()
        gateway.assert_not_called()

    def test_batch_requires_real_roundtrip_proof_before_opening_storage(self):
        args = SimpleNamespace(input=self.file, images=self.root, dry_run=False, proof=None)
        with patch('backend.scripts.recall_data.open_repository') as storage, self.assertRaisesRegex(PreparedDataError, 'one-record'):
            batch(args)
        storage.assert_not_called()

    def test_invalid_model_response_is_preserved_without_becoming_prepared_evidence(self):
        self.image.write_bytes(b'\x89PNG\r\n\x1a\nunit-test-image-placeholder')
        output = self.root / 'failed.json'

        class FixtureGateway:
            vision_model = 'unit-test-fixture'
            last_routing = {}

            async def __aenter__(self): return self
            async def __aexit__(self, *args): return None
            async def complete(self, *args, **kwargs): return '{"not":"canonical evidence"}'

        with patch('backend.scripts.recall_data.ModelGateway.from_env', return_value=FixtureGateway()):
            with self.assertRaises(EvidenceError):
                asyncio.run(extract(SimpleNamespace(output=output, image=self.image)))
        self.assertFalse(output.exists())
        invalid = list(self.root.glob('failed.invalid.*.json'))
        self.assertEqual(len(invalid), 1)
        self.assertEqual(json.loads(invalid[0].read_text())['raw_response'], '{"not":"canonical evidence"}')
