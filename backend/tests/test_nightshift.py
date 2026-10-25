"""Offline gateway checks: Nightshift routing and no NVIDIA fallback."""
import json
import os
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError, normalize_base_url


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def gateway(self, handler, model='meterless/vision'):
        transport = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncOpenAI(api_key='nightshift-test-token', base_url='http://localhost:8088/v1',
                             default_headers={'meterless-app': 'recall'},
                             http_client=transport, max_retries=0)
        with patch('backend.app.adapters.nightshift.AsyncOpenAI', return_value=client):
            return ModelGateway(base_url='http://localhost:8088/v1',
                                api_key='nightshift-test-token', model=model)

    def models(self, model='meterless/vision'):
        return httpx.Response(200, json={'object': 'list', 'data': [
            {'id': model, 'object': 'model', 'created': 0, 'owned_by': 'meterless'},
        ]})

    async def test_discovery_and_text_and_image_use_only_nightshift(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, 'localhost')
            self.assertEqual(request.headers['authorization'], 'Bearer nightshift-test-token')
            self.assertEqual(request.headers['meterless-app'], 'recall')
            if request.method == 'GET':
                return self.models()
            self.assertEqual(request.headers['meterless-scope'], 'user')
            body = json.loads(request.content)
            self.assertEqual(body['model'], 'meterless/vision')
            return httpx.Response(200, json={'id': 'test', 'object': 'chat.completion', 'created': 0,
                'model': 'meterless/vision', 'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': 'done'}}]})
        async with await self.gateway(handler) as gateway:
            self.assertEqual(await gateway.complete([{'role': 'user', 'content': 'Hello'}]), 'done')
            image_message = [{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,eA=='}},
                {'type': 'text', 'text': 'Read this image'},
            ]}]
            self.assertEqual(await gateway.complete(image_message), 'done')
        self.assertEqual([request.url.path for request in calls],
                         ['/v1/models', '/v1/chat/completions', '/v1/chat/completions'])
        self.assertEqual(json.loads(calls[-1].content)['messages'], image_message)

    async def test_unknown_model_never_sends_chat(self):
        calls = []
        def handler(request):
            calls.append(request)
            return self.models('meterless/text')
        async with await self.gateway(handler) as gateway:
            with self.assertRaisesRegex(ModelGatewayError, 'not advertised'):
                await gateway.complete([{'role': 'user', 'content': 'Hello'}])
        self.assertEqual(len(calls), 1)

    async def test_auth_failure_does_not_leak_body_or_fall_back(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(401, json={'error': {'message': 'nightshift-test-token'}})
        async with await self.gateway(handler) as gateway:
            with self.assertRaises(ModelGatewayError) as error:
                await gateway.complete([{'role': 'user', 'content': 'Hello'}])
        self.assertIn('credentials/access', str(error.exception))
        self.assertNotIn('nightshift-test-token', str(error.exception))
        self.assertEqual(len(calls), 1)

    async def test_connection_failure_does_not_use_nvidia(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ConnectError('private diagnostic', request=request)
        async with await self.gateway(handler) as gateway:
            with self.assertRaisesRegex(ModelGatewayError, 'no direct-provider fallback'):
                await gateway.complete([{'role': 'user', 'content': 'Hello'}])
        self.assertEqual(len(calls), 1)

    def test_nvidia_key_cannot_replace_missing_meterless_key(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'not-a-real-key',
                                   'METERLESS_BASE_URL': 'http://localhost:8088/v1'}, clear=True):
            with self.assertRaisesRegex(ModelGatewayError, 'Missing METERLESS_API_KEY'):
                ModelGateway.from_env()

    def test_direct_nvidia_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ModelGatewayError, 'forbidden'):
            ModelGateway(base_url='https://integrate.api.nvidia.com/v1', api_key='not-a-real-key')

    def test_bare_nvidia_model_id_is_not_guessed_as_nightshift_route(self):
        with self.assertRaisesRegex(ModelGatewayError, 'discovered'):
            ModelGateway(base_url='http://localhost:8088', api_key='not-a-real-key',
                         model='nvidia/nemotron-3.5-super-vl-120b-a12b')

    def test_base_url_normalization(self):
        for url in ['http://localhost:8088', 'http://localhost:8088/v1/',
                    'http://localhost:8088/v1/models', 'http://localhost:8088/v1/chat/completions',
                    'http://localhost:8088/healthz']:
            with self.subTest(url=url):
                self.assertEqual(normalize_base_url(url), 'http://localhost:8088/v1')
        for url in ['https://user:secret@localhost/v1', 'http://localhost/v1?key=secret']:
            with self.subTest(url=url), self.assertRaises(ModelGatewayError):
                normalize_base_url(url)


if __name__ == '__main__':
    unittest.main()
