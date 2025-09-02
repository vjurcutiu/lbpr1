from fastapi.testclient import TestClient
from components.apigateway.app import create_app

def _client():
    app = create_app()
    return TestClient(app)

AUTH = {"Authorization": "Bearer demo"}

def test_health():
    c = _client()
    r = c.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["status"] == "ok"

def test_create_ingestion_requires_auth():
    c = _client()
    r = c.post("/v1/ingestions", json={"tags": ["x"]})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["type"] == "AUTH_ERROR"

def test_create_ingestion_success():
    c = _client()
    r = c.post("/v1/ingestions", headers=AUTH, json={"tags": ["alpha"]})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["status"] == "pending"
    job_id = body["result"]["job_id"]

    r2 = c.post(f"/v1/ingestions/{job_id}/files", headers=AUTH, json={"uris": ["s3://demo/a.txt"]})
    assert r2.json()["ok"] is True
    assert r2.json()["result"]["files_total"] == 1

    r3 = c.post(f"/v1/ingestions/{job_id}/finalize", headers=AUTH, json={"dedupe": True})
    assert r3.json()["ok"] is True
    assert r3.json()["result"]["status"] == "completed"

def test_search_and_chat():
    c = _client()
    s = c.post("/v1/search", headers=AUTH, json={"query": "hello", "top_k": 5})
    assert s.json()["ok"] is True
    ch = c.post("/v1/chat/completions", headers=AUTH, json={"messages": [{"role":"user","content":"hi"}]})
    assert ch.json()["ok"] is True
    assert ch.json()["result"]["choices"][0]["message"]["content"] == "Hello!"
