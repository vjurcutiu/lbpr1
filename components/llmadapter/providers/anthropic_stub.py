from __future__ import annotations

"""
Anthropic provider stub.

TODO:
- Implement using Anthropic Messages API.
- Tool use mapping.
- Streaming chunks mapping to ChatDelta.
- Retries/backoff and error mapping.
"""

from typing import AsyncIterator

from ..contracts import ChatDelta, ChatRequest, ChatResponse, LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    async def generate(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError("Anthropic provider not implemented yet")

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        raise NotImplementedError("Anthropic provider not implemented yet")


