from __future__ import annotations

import os
import time
import uuid
from typing import AsyncIterator, Optional

from .contracts import (
    ChatDelta,
    ChatRequest,
    ChatResponse,
    InvalidRequestError,
    LLMProvider,
)
from .providers.fake import FakeProvider
from .providers.openai_stub import OpenAIProvider
from .providers.anthropic_stub import AnthropicProvider


def make_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "fake").lower()
    if provider == "openai":
        return OpenAIProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    return FakeProvider()


class LLMAdapterService:
    """
    Thin application service; all heavy lifting done in the provider.
    Adds request/span ids and basic timing fields into metadata.
    """

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self.provider = provider or make_provider()

    async def chat(self, req: ChatRequest) -> ChatResponse:
        req = self._with_ids(req)
        t0 = time.perf_counter()
        try:
            resp = await self.provider.generate(req)
        finally:
            _ = time.perf_counter() - t0
        return resp

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        req = self._with_ids(req)
        t0 = time.perf_counter()
        async for delta in self.provider.stream(req):
            yield delta
        _ = time.perf_counter() - t0

    def _with_ids(self, req: ChatRequest) -> ChatRequest:
        md = dict(req.metadata or {})
        md.setdefault("request_id", md.get("request_id") or str(uuid.uuid4()))
        md.setdefault("span_id", md.get("span_id") or str(uuid.uuid4()))
        # shallow copy with updated metadata
        return ChatRequest(**{**req.dict(exclude={"metadata"}), "metadata": md})


