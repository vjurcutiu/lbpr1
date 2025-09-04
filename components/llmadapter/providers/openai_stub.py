from __future__ import annotations

"""
OpenAI provider stub.

TODO:
- Implement using the official OpenAI Python SDK (Responses API).
- Map ChatRequest -> OpenAI request
- Map OpenAI response -> ChatResponse / ChatDelta
- Add retries/backoff and error mapping (rate limit, auth, timeout).
"""

from typing import AsyncIterator

from ..contracts import ChatDelta, ChatRequest, ChatResponse, LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    async def generate(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError("OpenAI provider not implemented yet")

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        raise NotImplementedError("OpenAI provider not implemented yet")


