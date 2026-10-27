"""Cover Agent: from a few candidate photos found on the web, choose the one that clearly shows this saved item, or refuse.

It only ever chooses among the images it is shown (never invents or edits one), and prefers no cover over a doubtful one. It does not see the person's own
screenshot, only the item's name and a short description. The model reply is a small JSON object that is validated here."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re
import uuid

from backend.app.adapters.nightshift import ModelGatewayError

PROMPT = """You choose the cover photo for one saved item in someone's personal collection.
Pick an image ONLY if it clearly shows this exact item: the named restaurant or cafe (its storefront, interior or signature food), the named product, or the named destination.
Reject any image that is: a different place or product with a similar name, a person or celebrity, a logo or text-only graphic, a map, a screenshot, a collage, watermarked, very low quality, or anything you are unsure about.
Prefer no cover over a doubtful one.
Reply with JSON only, no other text: {"choice": <index of the best image, or null if none qualifies>, "reason": "<one short sentence>"}"""


class CoverError(ValueError):
    pass


@dataclass(frozen=True)
class CoverChoice:
    index: int | None
    reason: str


def parse_choice(content: str, count: int) -> CoverChoice:
    match = re.search(r'\{.*\}', content or '', re.S)
    if not match:
        raise CoverError('The Cover Agent did not return JSON.')
    try:
        raw = json.loads(match.group(0))
    except ValueError:
        raise CoverError('The Cover Agent returned invalid JSON.') from None
    choice, reason = raw.get('choice'), raw.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise CoverError('The Cover Agent gave no reason.')
    if choice is None:
        return CoverChoice(None, reason.strip())
    if isinstance(choice, bool) or not isinstance(choice, int) or not 0 <= choice < count:
        raise CoverError('The Cover Agent chose an image it was not shown.')
    return CoverChoice(choice, reason.strip())


def _data_url(data: bytes) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')


class CoverAgent:
    def __init__(self, gateway):
        self.gateway = gateway

    async def choose(self, subject: str, description: str, images: list[bytes]) -> CoverChoice:
        model = self.gateway.vision_model
        if not model:
            raise ModelGatewayError('Missing METERLESS_VISION_MODEL; choose a vision model advertised by Nightshift.')
        content: list[dict] = [{'type': 'text', 'text': PROMPT},
                               {'type': 'text', 'text': json.dumps({'item': subject, 'about': description}, ensure_ascii=False)}]
        for i, data in enumerate(images):
            content += [{'type': 'text', 'text': f'Image {i}:'}, {'type': 'image_url', 'image_url': {'url': _data_url(data)}}]
        content.append({'type': 'text', 'text': f'request_id: {uuid.uuid4().hex}'})  # a fresh model call every time (Nightshift cache)
        reply = await self.gateway.complete([{'role': 'user', 'content': content}], model=model, max_tokens=300)
        return parse_choice(reply, len(images))
