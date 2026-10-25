"""Offline batch Evidence checks: no Nightshift, no real credentials, no network."""
import asyncio
import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.agents.evidence import EvidenceAgent, parse_evidence
from backend.scripts import batch_evidence as batch

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 16
MODEL = 'gpt-4o-mini'
GOOD_ROUTING = {'returned_model': MODEL, 'finish_reason': 'stop', 'requested_model': MODEL, 'routed_model': MODEL,
                'provider': 'openai', 'phase_models': [MODEL]}
EXTRACTION = {'domain': 'food', 'summary': 'A burger shop post.', 'sensitive': False, 'confidence': 'high', 'entities': [
    {'name': 'OMB Burger', 'type': 'restaurant', 'location': {'location_name': 'Melbourne CBD', 'city': 'Melbourne', 'country': None},
     'attributes': {'price': 'under $10'}}]}


class Vision:
    """Scripted vision gateway. Replies are JSON strings or exceptions."""
    vision_model = MODEL

    def __init__(self, *replies, routing=None):
        self.replies, self.routing, self.calls, self.last_routing = list(replies), routing or GOOD_ROUTING, [], {}

    async def complete(self, messages, *, max_tokens=2048, model=None):
        self.calls.append(model)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        self.last_routing = dict(self.routing)
        return reply


def extraction_json(**kw):
    return json.dumps({**EXTRACTION, **kw})


def artifact(name, **kw):
    parsed = asdict(parse_evidence(extraction_json()))
    return {'source_file': name, 'extraction': parsed, 'receipt': {k: GOOD_ROUTING[k] for k in batch.RECEIPT_KEYS}, **kw}


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.input, self.output = self.root / 'in', self.root / 'out'
        self.input.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def image(self, name):
        path = self.input / name
        path.write_bytes(PNG)
        return path

    def plans(self, **kw):
        return batch.make_plan(batch.discover_images(self.input), self.output, MODEL, 'openai', force=kw.get('force', False), limit=kw.get('limit'))

    def run_batch(self, gateway, plans, secrets=()):
        lines = []
        report = asyncio.run(batch.run_batch(plans, EvidenceAgent(gateway), gateway, MODEL, 'openai', list(secrets), out=lines.append))
        return report, lines


class DiscoveryTests(Workspace):
    def test_finds_supported_images_only_and_keeps_neutral_names(self):
        for name in ('IMG_0002.PNG', 'a1b2c3d4-0000-4000-8000-000000000001.JPG', 'shot.jpeg', 'x.webp'):
            self.image(name)
        (self.input / 'notes.txt').write_text('no')
        (self.input / '.hidden.png').write_bytes(PNG)
        (self.input / 'folder.png').mkdir()
        found = batch.discover_images(self.input)
        self.assertEqual([p.name for p in found], sorted(['IMG_0002.PNG', 'a1b2c3d4-0000-4000-8000-000000000001.JPG', 'shot.jpeg', 'x.webp']))
        self.assertEqual([p.output.name for p in self.plans()], [f'{p.stem}.json' for p in found])

    def test_stem_collisions_are_refused_before_any_work(self):
        self.image('a.png')
        self.image('a.jpg')
        with self.assertRaisesRegex(batch.BatchError, 'collide'):
            batch.discover_images(self.input)

    def test_missing_input_folder(self):
        with self.assertRaises(batch.BatchError):
            batch.discover_images(self.root / 'nope')


class ResumeTests(Workspace):
    def put(self, name, data):
        self.output.mkdir(exist_ok=True)
        path = self.output / f'{Path(name).stem}.json'
        path.write_text(data if isinstance(data, str) else json.dumps(data))
        return path

    def test_valid_existing_output_is_skipped_without_a_model_call(self):
        self.image('IMG_1.PNG')
        self.put('IMG_1.PNG', artifact('IMG_1.PNG'))
        gateway = Vision()
        report, lines = self.run_batch(gateway, self.plans())
        self.assertEqual((report.skipped, report.ok, gateway.calls), (1, 0, []))
        self.assertIn('SKIP', lines[0])

    def test_invalid_existing_outputs_are_regenerated(self):
        cases = {
            'garbage': 'not json {',
            'wrong schema': {**artifact('IMG_1.PNG'), 'extraction': {'domain': 'food'}},
            'wrong provider': {**artifact('IMG_1.PNG'), 'receipt': {**artifact('IMG_1.PNG')['receipt'], 'provider': 'nvidia'}},
            'wrong model': {**artifact('IMG_1.PNG'), 'receipt': {**artifact('IMG_1.PNG')['receipt'], 'routed_model': 'other'}},
            'wrong source': artifact('OTHER.PNG'),
            'extra field': {**artifact('IMG_1.PNG'), 'token': 'x'},
            'not canonical': {**artifact('IMG_1.PNG'), 'extraction': {**artifact('IMG_1.PNG')['extraction'], 'domain': 'FOOD'}},
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.image('IMG_1.PNG')
                self.put('IMG_1.PNG', data)
                gateway = Vision(extraction_json())
                report, _ = self.run_batch(gateway, self.plans())
                self.assertEqual((report.ok, len(gateway.calls)), (1, 1))
                self.assertIsNone(batch.existing_status(self.output / 'IMG_1.json', 'IMG_1.PNG', MODEL, 'openai'))

    def test_force_regenerates_valid_outputs(self):
        self.image('IMG_1.PNG')
        self.put('IMG_1.PNG', artifact('IMG_1.PNG'))
        gateway = Vision(extraction_json(summary='Regenerated.'))
        report, _ = self.run_batch(gateway, self.plans(force=True))
        self.assertEqual((report.ok, len(gateway.calls)), (1, 1))
        self.assertEqual(json.loads((self.output / 'IMG_1.json').read_text())['extraction']['summary'], 'Regenerated.')

    def test_limit_caps_model_calls(self):
        for i in range(3):
            self.image(f'IMG_{i}.PNG')
        plans = self.plans(limit=2)
        self.assertEqual([p.action for p in plans], ['process', 'process', 'skip'])
        gateway = Vision(extraction_json(), extraction_json())
        report, _ = self.run_batch(gateway, plans)
        self.assertEqual((report.ok, report.skipped, len(gateway.calls)), (2, 1, 2))


class OutputTests(Workspace):
    def test_success_writes_validated_extraction_and_sanitized_receipt(self):
        self.image('IMG_1.PNG')
        report, lines = self.run_batch(Vision(extraction_json()), self.plans())
        data = json.loads((self.output / 'IMG_1.json').read_text())
        self.assertEqual(report.ok, 1)
        self.assertEqual(set(data), {'source_file', 'extraction', 'receipt'})
        self.assertEqual(data['source_file'], 'IMG_1.PNG')
        self.assertEqual(data['extraction'], asdict(parse_evidence(extraction_json())))
        self.assertEqual(data['receipt'], {'requested_model': MODEL, 'routed_model': MODEL, 'provider': 'openai'})
        self.assertNotIn('finish_reason', json.dumps(data))
        self.assertEqual([l.split('  ')[1] for l in lines], ['PROCESSING', 'OK'])
        self.assertEqual([p.name for p in self.output.iterdir()], ['IMG_1.json'])  # no temp files left

    def test_wrong_provider_or_model_receipt_is_rejected_and_not_written(self):
        for routing in ({**GOOD_ROUTING, 'provider': 'nvidia'}, {**GOOD_ROUTING, 'routed_model': 'gemini-3.5-flash-lite'}):
            with self.subTest(routing=routing['provider'] + routing['routed_model']):
                self.image('IMG_1.PNG')
                report, lines = self.run_batch(Vision(extraction_json(), routing=routing), self.plans())
                self.assertEqual((report.ok, report.failed), (0, ['IMG_1.PNG']))
                self.assertIn('FAILED', lines[-1])
                self.assertFalse((self.output / 'IMG_1.json').exists())

    def test_one_failure_keeps_previous_outputs_and_the_batch_continues(self):
        self.image('IMG_1.PNG')
        self.image('IMG_2.PNG')
        first, _ = self.run_batch(Vision(extraction_json(summary='First.'), extraction_json()), self.plans())
        before = (self.output / 'IMG_1.json').read_bytes()
        gateway = Vision('not json', extraction_json(summary='Second.'))
        report, lines = self.run_batch(gateway, self.plans(force=True))
        self.assertEqual((report.ok, report.failed), (1, ['IMG_1.PNG']))
        self.assertEqual((self.output / 'IMG_1.json').read_bytes(), before)  # failed regeneration left the old valid file alone
        self.assertEqual(json.loads((self.output / 'IMG_2.json').read_text())['extraction']['summary'], 'Second.')
        self.assertTrue(any('FAILED' in l for l in lines))

    def test_failed_call_never_creates_an_output(self):
        self.image('IMG_1.PNG')
        report, _ = self.run_batch(Vision(RuntimeError('boom with detail')), self.plans())
        self.assertFalse(self.output.exists() and any(self.output.iterdir()))
        self.assertEqual(report.failed, ['IMG_1.PNG'])

    def test_unexpected_errors_are_reduced_to_a_class_name(self):
        self.image('IMG_1.PNG')
        _, lines = self.run_batch(Vision(RuntimeError('secret-detail')), self.plans())
        self.assertNotIn('secret-detail', '\n'.join(lines))
        self.assertIn('RuntimeError', lines[-1])

    def test_credentials_never_reach_an_output_file(self):
        self.image('IMG_1.PNG')
        leaky = extraction_json(summary='The key is sk-test-secret-12345678 in this screenshot.')
        report, lines = self.run_batch(Vision(leaky), self.plans(), secrets=['sk-test-secret-12345678'])
        self.assertEqual(report.failed, ['IMG_1.PNG'])
        self.assertFalse(self.output.exists() and any(self.output.iterdir()))
        self.assertNotIn('sk-test-secret', '\n'.join(lines))

    def test_unsupported_image_fails_without_a_model_call(self):
        (self.input / 'bad.png').write_bytes(b'not an image')
        gateway = Vision(extraction_json())
        report, _ = self.run_batch(gateway, self.plans())
        self.assertEqual((report.failed, gateway.calls), (['bad.png'], []))


class ServiceFailureTests(Workspace):
    def test_nightshift_unreachable_stops_the_batch(self):
        for i in range(5):
            self.image(f'IMG_{i}.PNG')
        gateway = Vision(ModelGatewayError('Nightshift cannot be reached; no direct-provider fallback was attempted.'), extraction_json())
        report, lines = self.run_batch(gateway, self.plans())
        self.assertEqual(len(gateway.calls), 1)
        self.assertIn('unavailable', report.stopped)
        self.assertTrue(lines[-1].startswith('STOPPED'))
        self.assertFalse(self.output.exists() and any(self.output.iterdir()))

    def test_repeated_gateway_failures_stop_instead_of_repeating(self):
        for i in range(6):
            self.image(f'IMG_{i}.PNG')
        gateway = Vision(*[ModelGatewayError('Nightshift request rejected (HTTP 502); raw response omitted.')] * 6)
        report, _ = self.run_batch(gateway, self.plans())
        self.assertEqual((len(gateway.calls), len(report.failed)), (3, 3))
        self.assertIn('consecutive', report.stopped)

    def test_a_success_resets_the_failure_streak(self):
        for i in range(5):
            self.image(f'IMG_{i}.PNG')
        bad = ModelGatewayError('Nightshift request rejected (HTTP 502); raw response omitted.')
        gateway = Vision(bad, bad, extraction_json(), bad, extraction_json())
        report, _ = self.run_batch(gateway, self.plans())
        self.assertEqual((report.ok, len(report.failed), report.stopped), (2, 3, None))


class DryRunTests(Workspace):
    def test_dry_run_makes_zero_model_calls_and_writes_nothing(self):
        for i in range(3):
            self.image(f'IMG_{i}.PNG')
        args = batch.argparse.Namespace(input=self.input, output=self.output, force=False, limit=None, dry_run=True, provider='openai')
        with patch.dict(os.environ, {'METERLESS_VISION_MODEL': MODEL}), patch.object(batch, 'load_dotenv'), \
                patch.object(batch.ModelGateway, 'from_env', side_effect=AssertionError('dry run must not build a gateway')), \
                patch.object(batch.EvidenceAgent, 'observe', side_effect=AssertionError('dry run must not call the model')):
            self.assertEqual(asyncio.run(batch.main_async(args)), 0)
        self.assertFalse(self.output.exists())

    def test_summary_counts_calls_and_valid_outputs(self):
        for i in range(3):
            self.image(f'IMG_{i}.PNG')
        self.output.mkdir()
        (self.output / 'IMG_0.json').write_text(json.dumps(artifact('IMG_0.PNG')))
        lines = []
        calls = batch.summarize(batch.discover_images(self.input), self.plans(), self.input, self.output, MODEL, 'openai', out=lines.append)
        text = '\n'.join(lines)
        self.assertEqual(calls, 2)
        self.assertIn('3 images found', text)
        self.assertIn('Already valid (skipped): 1', text)
        self.assertIn('Model calls required:    2', text)


if __name__ == '__main__':
    unittest.main()
