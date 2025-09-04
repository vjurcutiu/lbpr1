from __future__ import annotations

import asyncio
import hashlib
import time
from typing import AsyncIterator, List

from ..contracts import (
    ChatDelta,
    ChatRequest,
    ChatResponse,
    ChatResponseChoice,
    LLMProvider,
    PromptMessage,
    Usage,
)


class FakeProvider(LLMProvider):
    """
    Deterministic provider for tests:
    - Concatenates last user message with a predictable suffix.
    - Streaming splits the content into small chunks with tiny delays.
    """

    name = "fake"

    async def generate(self, req: ChatRequest) -> ChatResponse:
        user_last = _last_user_content(req)
        content = f"[fake:{req.model}] {user_last}".strip()
        msg = PromptMessage(role="assistant", content=content)
        usage = _fake_usage(req, content)
        rid = _rid(req)
        return ChatResponse(
            id=rid,
            model=req.model,
            provider=self.name,
            request_id=req.metadata.get("request_id"),
            span_id=req.metadata.get("span_id"),
            choices=[ChatResponseChoice(index=0, message=msg, finish_reason="stop")],
            usage=usage,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        user_last = _last_user_content(req)
        full = f"[fake:{req.model}] {user_last}".strip()
        rid = _rid(req)

        # Emit in 6-ish char chunks to make tests stable
        chunk_size = 6
        for i in range(0, len(full), chunk_size):
            await asyncio.sleep(0.001)  # tiny delay to simulate streaming
            yield ChatDelta(
                id=rid,
                model=req.model,
                content_delta=full[i : i + chunk_size],
                event="chunk",
            )
        # Final usage/end frame
        yield ChatDelta(
            id=rid,
            model=req.model,
            usage=_fake_usage(req, full),
            event="end",
        )


def _last_user_content(req: ChatRequest) -> str:
    # Prefer the last non-empty 'user' message; fallback to last message content.
    for m in reversed(req.messages):
        if m.role == "user" and m.content.strip():
            return m.content.strip()
    return req.messages[-1].content.strip()


def _rid(req: ChatRequest) -> str:
    h = hashlib.sha1()
    h.update(req.model.encode("utf-8"))
    last = _last_user_content(req).encode("utf-8")
    h.update(last)
    return "fake_" + h.hexdigest()[:16]


def _fake_usage(req: ChatRequest, completion: str) -> Usage:
    prompt_len = sum(len(m.content) for m in req.messages)
    completion_len = len(completion)
    total = prompt_len + completion_len
    # Not real tokens, but deterministic pseudo-counts for tests
    return Usage(prompt_tokens=prompt_len // 4, completion_tokens=completion_len // 4, total_tokens=total // 4)


