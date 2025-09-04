from fastapi import FastAPI
from fastapi.testclient import TestClient

from components.indexer.routes import get_router


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(get_router())
    return app


def test_routes_happy_path():
    app = make_app()
    client = TestClient(app)

    resp = client.post(
        "/indexer/jobs",
        json={
            "tenant_id": "t-1",
            "doc": {"text": "hello world " * 100, "metadata": {"title": "Hello"}},
            "options": {"chunk_size": 50, "chunk_overlap": 10, "vector_namespace": "docs"},
        },
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    job_id = job["job_id"]

    # get job
    resp2 = client.get(f"/indexer/jobs/{job_id}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["status"] in ("completed", "failed")
    assert "counts" in body

    # events
    resp3 = client.get(f"/indexer/jobs/{job_id}/events")
    assert resp3.status_code == 200
    ev = resp3.json()
    assert ev["job_id"] == job_id
    assert isinstance(ev["events"], list)
