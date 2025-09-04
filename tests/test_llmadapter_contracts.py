import asyncio
import json
import pytest

from components.llmadapter import (
    LLMAdapterService,
    ChatRequest,
    PromptMessage,
)


@pytest.mark.anyio
async def test_non_stream_chat_fake_provider_default():
    svc = LLMAdapterService()  # defaults to Fake
    req = ChatRequest(
        model="fake-small",
        messages=[PromptMessage(role="user", content="Hello world!")],
    )

    resp = await svc.chat(req)
    assert resp.model == "fake-small"
    assert resp.provider == "fake"
    assert resp.choices and resp.choices[0].message.content.startswith("[fake:fake-small] Hello world!")
    assert resp.usage.total_tokens >= 0
    assert resp.id.startswith("fake_")


@pytest.mark.anyio
async def test_stream_chat_ndjson_sequence():
    svc = LLMAdapterService()
    req = ChatRequest(
        model="fake-small",
        messages=[PromptMessage(role="user", content="stream me please")],
    )

    chunks = []
    async for delta in svc.chat_stream(req):
        chunks.append(delta)

    # last frame should be 'end'
    assert chunks[-1].event == "end"
    # content deltas before the end
    content = "".join([c.content_delta for c in chunks if c.content_delta])
    assert "[fake:fake-small] stream me please" in content


