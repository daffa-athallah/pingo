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


class ModelGateway:
    """Small async text/vision gateway; use with `async with` to close connections.

    Set METERLESS_MODEL to an exact meterless/* ID discovered on your instance.
    Ensure that mode is pinned to the verified Nemotron model in Nightshift.
    """

    def __init__(self, *, base_url: str, api_key: str, model: str | None = None):
        normalized = normalize_base_url(base_url)
        if not api_key.strip():
            raise ModelGatewayError('Missing METERLESS_API_KEY; NVIDIA_API_KEY is never used as a fallback.')
        if model and (not model.startswith('meterless/') or any(char.isspace() for char in model)):
            raise ModelGatewayError('METERLESS_MODEL must be an exact discovered meterless/* routing ID.')
        self.model = model
        self._verified = False
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
                   model=os.environ.get('METERLESS_MODEL', '').strip() or None)

    async def available_models(self) -> list[str]:
        """Discovery only, not proof that a route serves NVIDIA or accepts images."""
        try:
            models = await self._client.models.list()
            return sorted({item.id for item in models.data if item.id.startswith('meterless/')})
        except Exception as exc:
            raise safe_error(exc) from None

    async def complete(self, messages: list[ChatCompletionMessageParam], *, max_tokens: int = 2048) -> str:
        if not self.model:
            raise ModelGatewayError('Missing METERLESS_MODEL; discover available routes before choosing one.')
        if not messages or max_tokens <= 0:
            raise ModelGatewayError('Supply messages and a positive max_tokens budget.')
        if not self._verified:
            if self.model not in await self.available_models():
                raise ModelGatewayError('Configured METERLESS_MODEL is not advertised by Nightshift; no alternate route selected.')
            self._verified = True
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers={'meterless-scope': 'user'},
            )
        except Exception as exc:
            self._verified = False
            raise safe_error(exc) from None
        if not response.choices or response.choices[0].finish_reason == 'length':
            raise ModelGatewayError('Nightshift returned no complete choice; check the route and token budget.')
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ModelGatewayError('Nightshift returned no text content; verify this route supports text/vision chat.')
        return content.strip()

    async def __aenter__(self) -> ModelGateway:
        return self

    async def __aexit__(self, *args) -> None:
        await self._client.close()
