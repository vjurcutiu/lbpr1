import json
from fastapi.testclient import TestClient

from components.searchservice.service import create_app


def _client():
    app = create_app()
    return TestClient(app)


def test_health_ok():
    client = _client()
    r = client.get("/search/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["docs"] >= 1


def test_semantic_search_contract_law():
    client = _client()
    payload = {
        "query": "contract breach and remedies",
        "top_k": 3,
        "search_type": "semantic",
        "include_snippets": True,
        "metadata_fields": ["title", "tags"]
    }
    r = client.post("/search", headers={"X-Debug-Bypass-Auth": "1"}, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "query_id" in data and "hits" in data
    assert data["total"] >= 1
    # Expect Contract-related docs near top (docA/docE in sample)
    titles = [h["metadata"].get("title") for h in data["hits"]]
    assert any("Contract" in (t or "") for t in titles)


def test_filter_must_not_contract():
    client = _client()
    payload = {
        "query": "law overview",
        "top_k": 5,
        "search_type": "semantic",
        "filters": {
            "must": [],
            "should": [],
            "must_not": [{"field": "tags", "op": "contains", "value": "contract"}]
        },
        "metadata_fields": ["title", "tags"]
    }
    r = client.post("/search", headers={"X-Debug-Bypass-Auth": "1"}, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    for h in data["hits"]:
        assert "contract" not in h["metadata"].get("tags", [])


def test_auth_required_without_bypass():
    client = _client()
    payload = {"query": "anything"}
    r = client.post("/search", json=payload)
    assert r.status_code == 401

---

### Notes

* **Auth**: v0.1 uses `X-Debug-Bypass-Auth: 1` to return a fixed `tenant_id="test-tenant"` (matching seeded data). Wire to AuthService later.
* **Adapters**: Clean **ports** in `contracts.py`; **in-memory** adapters in `adapters_inmemory.py` so tests pass deterministically.
* **Fusion**: Enum is present; hybrid hooks are in place. Actual multi-retriever fusion lands in a next iteration.
* **Observability**: Request IDs + timings + logs; OTel spans can be added when we wire the shared tracer.
* **Business knobs** to consider in next pass: per-plan `top_k` caps, field allowlists, and per-tenant limits.

If you want, I can immediately:

1. add a **BM25/keyword** adapter skeleton and enable real **hybrid + RRF**;
2. wire an **AuthService token decoder** stub;
3. expose **/search/debug/example** to dump current sample corpus.
