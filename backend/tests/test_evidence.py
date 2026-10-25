"""Offline Evidence Agent checks; no screenshot or credential leaves the process."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from backend.app.adapters.nightshift import ModelGateway, ModelGatewayError
from backend.app.agents.evidence import (EVIDENCE_PROMPT, EvidenceAgent, EvidenceError, Location,
                                         image_data_url, parse_evidence)

GOOD = {'domain': 'Food', 'summary': 'A burger shop video.', 'entities': [
    {'name': 'OMB Burger', 'type': 'restaurant', 'category': 'restaurant', 'subcategory': None, 'brand': None,
     'location': {'location_name': 'Melbourne CBD', 'city': 'Melbourne', 'country': None},
     'attributes': {'price': 'under $10', 'halal': 'yes'}}],
    'sensitive': False, 'confidence': 'high'}
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 16


class ParseTests(unittest.TestCase):
    def test_valid_and_fenced(self):
        evidence = parse_evidence('```json\n' + json.dumps(GOOD) + '\n```')
        self.assertEqual(evidence.domain, 'food')
        self.assertEqual(evidence.entities[0].location, Location('Melbourne CBD', 'Melbourne', None))
        self.assertFalse(hasattr(evidence, 'possible_intent'))

    def test_possible_intent_is_rejected(self):
        with self.assertRaises(EvidenceError):
            parse_evidence(json.dumps({**GOOD, 'possible_intent': 'wants dinner'}))
        self.assertNotIn('possible_intent', EVIDENCE_PROMPT)
        self.assertNotIn('intent', EVIDENCE_PROMPT.lower().replace('do not guess what the user wants to do', ''))

    def test_location_is_moved_out_of_attributes_not_duplicated(self):
        entity = {'name': 'OMB Burger', 'type': 'restaurant', 'location': None,
                  'attributes': {'location': 'Melbourne CBD', 'City': 'Melbourne', 'price': 'under $10'}}
        parsed = parse_evidence(json.dumps({**GOOD, 'entities': [entity]})).entities[0]
        self.assertEqual(parsed.attributes, {'price': 'under $10'})
        self.assertEqual(parsed.location, Location('Melbourne CBD', 'Melbourne', None))

    def test_structured_location_wins_over_attribute_and_empty_location_is_null(self):
        entity = {'name': 'X', 'type': 'venue', 'location': {'location_name': 'Shibuya', 'city': None, 'country': None},
                  'attributes': {'location': 'Elsewhere'}}
        self.assertEqual(parse_evidence(json.dumps({**GOOD, 'entities': [entity]})).entities[0].location.location_name, 'Shibuya')
        empty = {'name': 'X', 'type': 'venue', 'location': {'location_name': ' ', 'city': None, 'country': None}}
        self.assertIsNone(parse_evidence(json.dumps({**GOOD, 'entities': [empty]})).entities[0].location)
        for bad in ({'street': '1 Main St'}, 'Melbourne'):
            with self.assertRaises(EvidenceError):
                parse_evidence(json.dumps({**GOOD, 'entities': [{**empty, 'location': bad}]}))

    def test_rejects_bad_shapes(self):
        for bad in ('not json', json.dumps({**GOOD, 'extra': 1}), json.dumps({**GOOD, 'sensitive': 'no'}),
                    json.dumps({**GOOD, 'confidence': 'sure'}), json.dumps({**GOOD, 'entities': [{'name': 'x'}]}), json.dumps({**GOOD, 'entities': [{'name': 'x', 'type': 'y', 'extra': 1}]}),
                    json.dumps({**GOOD, 'summary': ' '})):
            with self.subTest(bad=bad[:30]), self.assertRaises(EvidenceError):
                parse_evidence(bad)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def agent(self, handler, vision_model='gpt-4o-mini'):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncOpenAI(api_key='nightshift-test-token', base_url='http://localhost:8088/v1',
                             http_client=http, max_retries=0)
        with patch('backend.app.adapters.nightshift.AsyncOpenAI', return_value=client):
            gateway = ModelGateway(base_url='http://localhost:8088', api_key='nightshift-test-token',
                                   vision_model=vision_model)
        return gateway

    async def test_sends_image_to_vision_model_via_nightshift(self):
        sent = []
        def handler(request):
            if request.method == 'GET':
                return httpx.Response(200, json={'object': 'list', 'data': [
                    {'id': 'gpt-4o-mini', 'object': 'model', 'created': 0, 'owned_by': 'x'}]})
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'id': 't', 'object': 'chat.completion', 'created': 0, 'model': 'gpt-4o-mini',
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': json.dumps(GOOD)}}]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'private-name.png'
            path.write_bytes(PNG)
            async with await self.agent(handler) as gateway:
                evidence = await EvidenceAgent(gateway).observe(path)
        self.assertEqual(evidence.entities[0].name, 'OMB Burger')
        self.assertEqual(sent[0]['model'], 'gpt-4o-mini')
        parts = sent[0]['messages'][0]['content']
        self.assertTrue(parts[0]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertNotIn('private-name', json.dumps(sent[0]))

    async def test_missing_vision_model_never_sends(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(500)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.png'
            path.write_bytes(PNG)
            async with await self.agent(handler, vision_model=None) as gateway:
                with self.assertRaisesRegex(ModelGatewayError, 'METERLESS_VISION_MODEL'):
                    await EvidenceAgent(gateway).observe(path)
        self.assertEqual(calls, [])


class ImageTests(unittest.TestCase):
    def test_rejects_non_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.txt'
            path.write_text('hello')
            with self.assertRaises(EvidenceError):
                image_data_url(path)


if __name__ == '__main__':
    unittest.main()
