"""Strict replay at the model boundary. Replies are captured from Nightshift, never invented.

Only request nonces are ignored. Models, prompts, image hashes, evidence, clock and
context must match the recording exactly; stale or unrelated requests fail closed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from backend.app.adapters.nightshift import ModelGatewayError
from backend.app.observe import sanitize_receipt

DIRECTORY = Path(__file__).resolve().parents[1] / 'demo/recordings'


def request_signature(messages, kwargs):
    messages = deepcopy(messages)
    for message in messages:
        content = message.get('content')
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except ValueError:
                continue
            if isinstance(payload, dict):
                payload.pop('request_id', None)
                message['content'] = payload
        elif isinstance(content, list):
            message['content'] = [part for part in content if not (part.get('type') == 'text' and part.get('text', '').startswith('request_id: '))]
            for part in message['content']:
                if part.get('type') == 'image_url':
                    part['image_url'] = {'sha256': hashlib.sha256(part['image_url']['url'].encode()).hexdigest()}
    return hashlib.sha256(json.dumps({'messages': messages, 'options': kwargs}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class CapturingGateway:
    """Opt-in local capture of final structured replies, after the gateway strips reasoning."""
    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def last_routing(self):
        return self.inner.last_routing

    @last_routing.setter
    def last_routing(self, value):
        self.inner.last_routing = value

    async def complete(self, messages, **kwargs):
        reply = await self.inner.complete(messages, **kwargs)
        # Captures no input text, image data, credentials, headers or reasoning.
        self.calls.append({'signature': request_signature(messages, kwargs), 'reply': reply,
                           'receipt': sanitize_receipt(self.last_routing)})
        return reply


class RecordedGateway:
    def __init__(self, recording):
        self.vision_model = recording['vision_model']
        self.reasoning_model = recording['reasoning_model']
        self.calls = deepcopy(recording['calls'])
        self.position = 0
        self.last_routing = {}

    async def complete(self, messages, **kwargs):
        self.last_routing = {}
        if self.position >= len(self.calls):
            raise ModelGatewayError('Recording exhausted; no live or scripted fallback.')
        call = self.calls[self.position]
        if request_signature(messages, kwargs) != call['signature']:
            raise ModelGatewayError('Input differs from the recording; choose a bundled sample case.')
        self.position += 1
        self.last_routing = dict(call['receipt'] or {})
        return call['reply']

    def assert_consumed(self):
        if self.position != len(self.calls):
            raise ModelGatewayError('Replay did not consume every recorded response.')


def load_recording(case):
    if not case or any(c not in 'abcdefghijklmnopqrstuvwxyz_' for c in case):
        raise ValueError('Unknown recorded case.')
    path = DIRECTORY / f'{case}.json'
    if not path.is_file():
        raise ValueError('Unknown recorded case.')
    return json.loads(path.read_text())
