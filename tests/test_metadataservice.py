import json
from fastapi.testclient import TestClient

from components.metadataservice.service import create_app, deps_singleton, InMemoryBlobReader
from components.metadataservice.contracts import ExtractRequest, ExtractTextInput, ExtractBlobInput, ExtractOptions


def test_extract_text_basic():
    app = create_app()
    client = TestClient(app)

    req = {
        "input": {"kind": "text", "text": "Hello World\nThis is a sample document.\n", "source_id": "doc-1"},
        "options": {"tenant_id": "t1", "llm": {"enabled": False}, "keyword": {"top_k": 5}, "store": {"persist": True}},
    }

    res = client.post("/metadata/extract", json=req)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    record = body["data"]["record"]
    assert record["tenant_id"] == "t1"
    assert record["stats"]["words"] > 0
    assert len(record["keywords"]) > 0
    assert record["mime_guess"] == "text/plain"


def test_extract_blob_and_get():
    # seed a blob
    deps_singleton.blob_reader = InMemoryBlobReader(
        blobs={"mem://bucket/key.txt": b"Contract Agreement between Parties A and B.\nAmount due: 1000 EUR.\n"}
    )

    app = create_app()
    client = TestClient(app)

    req = {
        "input": {"kind": "blob", "blob_uri": "mem://bucket/key.txt", "source_id": "doc-blob-1"},
        "options": {"tenant_id": "tenantX", "llm": {"enabled": True}, "keyword": {"top_k": 7}, "store": {"persist": True}},
    }

    res = client.post("/metadata/extract", json=req)
    assert res.status_code == 200, res.text
    body = res.json()
    record = body["data"]["record"]
    assert record["tenant_id"] == "tenantX"
    assert "summary" in record
    assert record["summary"] is not None
    assert "categories" in record
    assert "legal" in record["categories"] or "finance" in record["categories"]

    # fetch by id
    mid = record["metadata_id"]
    res2 = client.get(f"/metadata/{mid}", params={"tenant_id": "tenantX"})
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    assert body2["ok"] is True
    assert body2["data"]["metadata_id"] == mid


def test_error_blob_not_found():
    app = create_app()
    client = TestClient(app)

    req = {
        "input": {"kind": "blob", "blob_uri": "mem://missing/blob"},
        "options": {"tenant_id": "t1", "llm": {"enabled": False}, "keyword": {"top_k": 5}, "store": {"persist": False}},
    }
    res = client.post("/metadata/extract", json=req)
    assert res.status_code == 404
    body = res.json()
    assert body["detail"]["code"] == "metadata.blob_not_found"

---

### Notes & next step options

* This iteration is self-contained and testable (in-memory).
* When you’re ready, we can wire real adapters:

  * **BlobReaderPort** → your BlobStorageAdapter (S3/GCS/Azure/local).
  * **LLMAdapterPort** → your existing LLMAdapter (model + prompts).
  * **MetadataStorePort** → Postgres via SQLAlchemy + Alembic.

If you want me to immediately add the Postgres adapter (models + alembic migration + repo + DI), say the word and I’ll ship the full files in the same style.
