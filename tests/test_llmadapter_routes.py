import os
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from components.llmadapter.routes import router

app = FastAPI()
app.include_router(router)


@pytest.fixture(autouse=True)
def _use_fake_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")


def test_http_chat_non_stream():
    client = TestClient(app)
    payload = {
        "model": "fake-small",
        "messages": [{"role": "user", "content": "ping"}],
    }
    r = client.post("/v1/llm/chat", json=payload, headers={"X-Request-Id": "req-123"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["model"] == "fake-small"
    assert data["provider"] == "fake"
    assert data["request_id"] == "req-123"
    assert data["choices"][0]["message"]["content"].startswith("[fake:fake-small] ping")


def test_http_chat_stream_ndjson():
    client = TestClient(app)
    payload = {
        "model": "fake-small",
        "messages": [{"role": "user", "content": "stream now"}],
    }
    r = client.post("/v1/llm/chat/stream", json=payload, headers={"X-Request-Id": "abc"})
    assert r.status_code == 200
    # NDJSON stream in a single testclient response (accumulated)
    lines = [ln for ln in r.text.strip().split("\n") if ln.strip()]
    assert lines[-1] and json.loads(lines[-1])["event"] == "end"
    content = "".join(json.loads(l).get("content_delta", "") for l in lines[:-1])
    assert "[fake:fake-small] stream now" in content

---

### Notes & next steps

* This is a clean first cut that you can mount into your FastAPI app with `include_router(components.llmadapter.routes.router)`.
* By default it uses the deterministic Fake provider, so tests don’t require external APIs.
* When you want real calls, set `LLM_PROVIDER=openai` or `anthropic` and implement the stubs.
* If you already have a centralized DI container, we can wire `get_service()` to resolve the provider there.

Want me to hook this into your existing `ApiGateway` or `ChatService` next, or implement the OpenAI provider with retries and token accounting?
