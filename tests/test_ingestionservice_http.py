import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from components.ingestionservice.contracts import IngestionStatus
from components.ingestionservice.http import router, set_ports_for_ingestion
from components.ingestionservice.ports import BlobStorageAdapterPort, IndexerPort, MetadataServicePort


# ---- Fakes reused for HTTP tests ----
class FakeBlob(BlobStorageAdapterPort):
    def put_bytes(self, tenant_id: str, path_hint: str, raw: bytes, content_type: str) -> str:
        return f"blob://{tenant_id}/{path_hint}"


class FakeMeta(MetadataServicePort):
    def upsert_file(self, tenant_id: str, blob_uri: str, filename: str, content_type: str, size_bytes: int, extra=None) -> str:
        return f"meta-{filename}"


class FakeIndexer(IndexerPort):
    def create_job(self, tenant_id: str, items):
        return "index-job-1"


def make_app():
    app = FastAPI()
    app.include_router(router)
    set_ports_for_ingestion(FakeBlob(), FakeMeta(), FakeIndexer())
    return app


def test_http_create_and_get_job():
    app = make_app()
    client = TestClient(app)

    raw = b"alpha"
    payload = {
        "files": [
            {
                "filename": "alpha.txt",
                "bytes_b64": base64.b64encode(raw).decode("ascii"),
                "content_type": "text/plain",
            }
        ]
    }
    r = client.post("/ingestions", json=payload, headers={"X-Tenant-Id": "tenant-42"})
    assert r.status_code == 201, r.text
    body = r.json()
    job = body["job"]
    assert job["status"] in (IngestionStatus.SUBMITTED_TO_INDEXER, IngestionStatus.FAILED)
    job_id = job["id"]

    r2 = client.get(f"/ingestions/{job_id}", headers={"X-Tenant-Id": "tenant-42"})
    assert r2.status_code == 200
    assert r2.json()["id"] == job_id

    r3 = client.get(f"/ingestions/{job_id}/events", headers={"X-Tenant-Id": "tenant-42"})
    assert r3.status_code == 200
    events = r3.json()["events"]
    assert any(ev["type"] == "indexer.submitted" for ev in events)

