import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from components.chatservice import chatservice_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(chatservice_router)
    return app


def test_create_chat_and_send_message(app):
    client = TestClient(app)

    # Create chat
    r = client.post("/chats?tenant_id=t1", json={"title": "My Chat"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    chat_id = data["data"]["chat"]["id"]

    # Post a user message (sync)
    r2 = client.post(f"/chats/{chat_id}/messages?tenant_id=t1", json={"content": "Hello!"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["ok"] is True
    assert "You said: Hello!" in data2["data"]["assistant_message"]["content"]

    # List messages
    r3 = client.get(f"/chats/{chat_id}/messages?tenant_id=t1")
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["ok"] is True
    assert len(data3["data"]["items"]) == 2


def test_tenant_mismatch_403(app):
    client = TestClient(app)

    r = client.post("/chats?tenant_id=A", json={"title": "A1"})
    chat_id = r.json()["data"]["chat"]["id"]

    r2 = client.get(f"/chats/{chat_id}?tenant_id=B")
    assert r2.status_code == 403


