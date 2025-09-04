from fastapi.testclient import TestClient

from components.embeddingadapter.service import make_app


def test_post_embeddings_fake_provider():
    app = make_app(provider="fake")
    client = TestClient(app)

    payload = {
        "texts": ["alpha", "beta"],
        "model": "route-test-model",
        "dimensions": 16,
        "normalize": True,
        "truncate": "NONE",
        "metadata": {"req_id": "abc-123"}
    }
    resp = client.post("/v1/embeddings", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["model"] == "route-test-model"
    assert data["dimensions"] == 16
    assert data["provider"] == "fake"
    assert len(data["vectors"]) == 2
    assert len(data["vectors"][0]) == 16

