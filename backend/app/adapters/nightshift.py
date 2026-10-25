"""Production model boundary: Recall -> Nightshift -> configured NVIDIA provider.

NVIDIA credentials are deliberately not read here. Provider pinning is configured
inside Nightshift; a successful routing-mode call alone does not prove NVIDIA use.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError
from openai.types.chat import ChatCompletionMessageParam


class ModelGatewayError(RuntimeError):
    """Safe configuration/availability error, without provider response dumps."""


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ModelGatewayError('METERLESS_BASE_URL must be an HTTP(S) Nightshift URL without credentials, query, or fragment.')
    host = parsed.hostname.lower().rstrip('.')
    if host == 'nvidia.com' or host.endswith('.nvidia.com'):
        raise ModelGatewayError('Direct NVIDIA endpoints are forbidden in the production Nightshift gateway.')
    path = parsed.path.rstrip('/')
    for suffix in ('/v1/chat/completions', '/v1/models', '/healthz', '/v1'):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path + '/v1', '', ''))


def safe_error(exc: Exception) -> ModelGatewayError:
    if isinstance(exc, APITimeoutError):
        return ModelGatewayError('Nightshift timed out; no direct-provider fallback was attempted.')
    if isinstance(exc, APIConnectionError):
        return ModelGatewayError('Nightshift cannot be reached; no direct-provider fallback was attempted.')
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        if status in (401, 403):
            return ModelGatewayError(f'Nightshift credentials/access rejected (HTTP {status}).')
        if status == 404:
            return ModelGatewayError('Nightshift route or endpoint unavailable (HTTP 404).')
        if status == 429:
            return ModelGatewayError('Nightshift rate limit or quota reached (HTTP 429).')
        return ModelGatewayError(f'Nightshift request rejected (HTTP {status}); raw response omitted.')
    return ModelGatewayError('Nightshift returned an invalid response; raw response omitted.')


def strip_reasoning(text: str) -> str:
    """Drop leaked chain-of-thought. Nemotron via Nightshift can return an
    unopened `reasoning...</think>answer`, so keep only what follows the last tag."""
    return text.rsplit('</think>', 1)[-1].strip() if '</think>' in text else text.strip()


def extract_routing(response) -> dict:
    """Non-secret routing evidence: Nightshift's compute receipt, if returned."""
    receipt = (response.model_extra or {}).get('meterless')
    receipt = receipt if isinstance(receipt, dict) else {}
    route = receipt.get('winning_route') if isinstance(receipt.get('winning_route'), dict) else {}
    return {
        'returned_model': response.model,
        'finish_reason': response.choices[0].finish_reason if response.choices else None,
        'requested_model': receipt.get('requested_model'),
        'routed_model': receipt.get('routed_model'),
        'provider': route.get('provider'),
        'phase_models': [p.get('model') for p in receipt.get('phases', []) if isinstance(p, dict)],
    }


class ModelGateway:
    """Small async text/vision gateway; use with `async with` to close connections.

    Models are exact IDs advertised by this Nightshift instance, checked against
    discovery before first use. METERLESS_MODEL is the default; METERLESS_VISION_MODEL
    (perception) and METERLESS_REASONING_MODEL (Nemotron) are used by the agents.
    """

    def __init__(self, *, base_url: str, api_key: str, model: str | None = None,
                 vision_model: str | None = None, reasoning_model: str | None = None):
        normalized = normalize_base_url(base_url)
        if not api_key.strip():
            raise ModelGatewayError('Missing METERLESS_API_KEY; NVIDIA_API_KEY is never used as a fallback.')
        for candidate in (model, vision_model, reasoning_model):
            if candidate and (any(char.isspace() for char in candidate) or '://' in candidate):
                raise ModelGatewayError('Model settings must be exact model IDs discovered from Nightshift.')
        self.model = model
        self.vision_model = vision_model
        self.reasoning_model = reasoning_model
        self.last_routing: dict = {}
        self._verified: set[str] = set()
        self._client = AsyncOpenAI(
            base_url=normalized,
            api_key=api_key.strip(),
            default_headers={'meterless-app': 'recall'},
            timeout=180,
            max_retries=0,
        )

    @classmethod
    def from_env(cls) -> ModelGateway:
        base_url = os.environ.get('METERLESS_BASE_URL', '').strip()
        if not base_url:
            raise ModelGatewayError('Missing METERLESS_BASE_URL; configure your Nightshift instance explicitly.')
        return cls(base_url=base_url,
                   api_key=os.environ.get('METERLESS_API_KEY', ''),
                   model=os.environ.get('METERLESS_MODEL', '').strip() or None,
                   vision_model=os.environ.get('METERLESS_VISION_MODEL', '').strip() or None,
                   reasoning_model=os.environ.get('METERLESS_REASONING_MODEL', '').strip() or None)

    async def available_models(self) -> list[str]:
        """Discovery only, not proof that a route serves NVIDIA or accepts images."""
        try:
            models = await self._client.models.list()
            return sorted({item.id for item in models.data})
        except Exception as exc:
            raise safe_error(exc) from None

    async def complete(self, messages: list[ChatCompletionMessageParam], *, max_tokens: int = 2048,
                       model: str | None = None) -> str:
        model = model or self.model
        if not model:
            raise ModelGatewayError('Missing model; set METERLESS_MODEL or pass one discovered from Nightshift.')
        if not messages or max_tokens <= 0:
            raise ModelGatewayError('Supply messages and a positive max_tokens budget.')
        if model not in self._verified:
            if model not in await self.available_models():
                raise ModelGatewayError('Configured model is not advertised by Nightshift; no alternate route selected.')
            self._verified.add(model)
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers={'meterless-scope': 'user'},
            )
        except Exception as exc:
            self._verified.discard(model)
            raise safe_error(exc) from None
        if not response.choices or response.choices[0].finish_reason == 'length':
            raise ModelGatewayError('Nightshift returned no complete choice; check the route and token budget.')
        content = response.choices[0].message.content
        if isinstance(content, str):
            content = strip_reasoning(content)
        if not isinstance(content, str) or not content.strip():
            raise ModelGatewayError('Nightshift returned no text content; verify this route supports text/vision chat.')
        self.last_routing = extract_routing(response)
        return content.strip()

    async def __aenter__(self) -> ModelGateway:
        return self

    async def __aexit__(self, *args) -> None:
        await self._client.close()
