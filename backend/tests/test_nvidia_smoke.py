"""Offline protocol and privacy checks; these do not prove NVIDIA access."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from backend.scripts import test_nvidia as smoke


class NvidiaSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Header fixture only: actual vision is never claimed by offline tests.
        self.image = Path(self.temp.name) / 'filename-must-not-reach-model.png'
        self.image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.env = patch.dict(os.environ, {
            'NVIDIA_API_KEY': 'unit-test-credential-not-real',
            'NVIDIA_BASE_URL': 'https://integrate.api.nvidia.com/v1',
            'NVIDIA_MODEL': smoke.PREFERRED_MODEL,
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dotenv = patch.object(smoke, 'load_dotenv')
        self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    def args(self, **overrides):
        values = dict(text_only=False, image=self.image, list_models=False, show_result=False)
        return argparse.Namespace(**(values | overrides))

    def execute(self, handler, **options):
        with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
            client = OpenAI(api_key='unit-test-credential-not-real',
                            base_url='https://integrate.api.nvidia.com/v1',
                            http_client=transport, max_retries=0)
            output = io.StringIO()
            with patch.object(smoke, 'OpenAI', return_value=client), redirect_stdout(output):
                code = smoke.run(self.args(**options))
            return code, output.getvalue()

    def completion(self, content):
        return httpx.Response(200, json={
            'id': 'offline', 'object': 'chat.completion', 'created': 0,
            'model': smoke.PREFERRED_MODEL,
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': content}}],
        })

    def test_text_precedes_image_and_filename_is_never_transmitted(self):
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(request.url.path, '/v1/chat/completions')
            if len(requests) == 1:
                return self.completion(smoke.TEXT_MARKER)
            self.assertNotIn(self.image.name, request.content.decode())
            content = body['messages'][0]['content']
            self.assertEqual(content[0]['image_url']['url'], smoke.image_data_url(self.image))
            return self.completion(json.dumps({
                'description': 'Private screenshot description',
                'visible_text': ['Private text'], 'possible_entities': [],
            }))
        code, output = self.execute(handler)
        self.assertEqual(code, 0)
        self.assertEqual(len(requests), 2)
        self.assertNotIn('Private screenshot description', output)
        self.assertNotIn('Private text', output)
        self.assertIn('[PASS] Text inference works', output)

    def test_text_only_never_sends_an_image(self):
        calls = []
        def handler(request):
            calls.append(request)
            return self.completion(smoke.TEXT_MARKER)
        code, _ = self.execute(handler, text_only=True, image=None)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIsInstance(json.loads(calls[0].content)['messages'][0]['content'], str)

    def test_missing_key_stops_before_creating_client(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': ''}), patch.object(smoke, 'OpenAI') as client:
            with self.assertRaisesRegex(smoke.SmokeFailure, 'Missing NVIDIA_API_KEY'):
                smoke.run(self.args())
            client.assert_not_called()

    def test_credentials_never_go_to_another_host(self):
        with patch.dict(os.environ, {'NVIDIA_BASE_URL': 'https://unrelated.invalid/v1'}):
            with self.assertRaisesRegex(smoke.SmokeFailure, 'NVIDIA_BASE_URL'):
                smoke.run(self.args())

    def test_auth_error_body_is_not_logged(self):
        def handler(request):
            return httpx.Response(401, json={'error': {'message': 'unit-test-credential-not-real', 'type': 'auth'}})
        code, output = self.execute(handler)
        self.assertEqual(code, 1)
        self.assertIn('credential/access failure', output)
        self.assertNotIn('unit-test-credential-not-real', output)

    def test_unavailable_model_lists_candidates_without_fallback(self):
        paths = []
        def handler(request):
            paths.append(request.url.path)
            if request.method == 'GET':
                return httpx.Response(200, json={'object': 'list', 'data': [
                    {'id': 'nvidia/nemotron-candidate', 'object': 'model', 'created': 0, 'owned_by': 'nvidia'},
                ]})
            return httpx.Response(404, json={'error': {'message': 'unavailable', 'type': 'not_found'}})
        code, output = self.execute(handler)
        self.assertEqual(code, 1)
        self.assertEqual(paths, ['/v1/chat/completions', '/v1/models'])
        self.assertNotIn('[PASS]', output)

    def test_invalid_text_stops_before_vision(self):
        with self.assertRaisesRegex(smoke.SmokeFailure, 'required marker'):
            self.execute(lambda request: self.completion('Not the marker'))

    def test_rejected_image_is_not_claimed_as_verified(self):
        def handler(request):
            content = json.loads(request.content)['messages'][0]['content']
            if isinstance(content, str):
                return self.completion(smoke.TEXT_MARKER)
            return httpx.Response(415, json={'error': {'message': 'unsupported', 'type': 'invalid'}})
        code, output = self.execute(handler)
        self.assertEqual(code, 1)
        self.assertIn('image support, encoding, or size', output)
        self.assertNotIn('[PASS] Local image', output)

    def test_image_schema_is_validated(self):
        for text in ('not JSON', '[]', '{"description": "x"}',
                     '{"description": "x", "visible_text": "wrong", "possible_entities": []}'):
            with self.subTest(text=text), self.assertRaises(smoke.SmokeFailure):
                smoke.parse_vision_result(text)
        self.assertEqual(smoke.parse_vision_result('```json\n{"description":"x","visible_text":[],"possible_entities":[]}\n```')['description'], 'x')

    def test_rate_limit_message_is_explicit(self):
        code, output = self.execute(lambda request: httpx.Response(429, json={'error': {'message': 'quota'}}))
        self.assertEqual(code, 1)
        self.assertIn('rate limit or quota', output)


if __name__ == '__main__':
    unittest.main()
