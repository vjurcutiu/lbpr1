import base64
from typing import Any, Dict, List

import pytest

from components.ingestionservice.contracts import (
    CreateIngestionRequest,
    IngestionStatus,
)
from components.ingestionservice.ports import BlobStorageAdapterPort, IndexerPort, MetadataServicePort
from components.ingestionservice.repository import InMemoryIngestionRepo
from components.ingestionservice.service import IngestionService


# ---- Fakes ----
class FakeBlob(BlobStorageAdapterPort):
    def __init__(self) -> None:
        self.stored: List[Dict[str, Any]] = []

    def put_bytes(self, tenant_id: str, path_hint: str, raw: bytes, content_type: str) -> str:
        self.stored.append(
            {"tenant_id": tenant_id, "path_hint": path_hint, "size": len(raw), "content_type": content_type}
        )
        return f"blob://{tenant_id}/{path_hint}"


class FakeMeta(MetadataServicePort):
    def __init__(self) -> None:
        self.upserts: List[Dict[str, Any]] = []

    def upsert_file(
        self,
        tenant_id: str,
        blob_uri: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        extra=None,
    ) -> str:
        self.upserts.append(
            {
                "tenant_id": tenant_id,
                "blob_uri": blob_uri,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "extra": extra,
            }
        )
        return f"meta-{filename}"


class FakeIndexer(IndexerPort):
    def __init__(self) -> None:
        self.jobs: List[List[Dict[str, Any]]] = []

    def create_job(self, tenant_id: str, items: List[Dict[str, Any]]) -> str:
        self.jobs.append(items)
        return f"index-job-{len(self.jobs)}"


# ---- Tests ----
def test_create_ingestion_with_inline_file_success():
    tenant_id = "t-1"
    repo = InMemoryIngestionRepo()
    blob = FakeBlob()
    meta = FakeMeta()
    indexer = FakeIndexer()

    svc = IngestionService(tenant_id=tenant_id, repo=repo, blob=blob, meta=meta, indexer=indexer)

    raw = b"hello world"
    req = CreateIngestionRequest(
        files=[
            {
                "filename": "hello.txt",
                "bytes_b64": base64.b64encode(raw).decode("ascii"),
                "content_type": "text/plain",
            }
        ]
    )

    job = svc.create_ingestion(req)
    assert job.status.name in ("SUBMITTED_TO_INDEXER", "FAILED")
    assert job.items and job.items[0].blob_uri.startswith("blob://t-1/hello.txt")
    assert job.index_job_id is not None
    assert len(indexer.jobs) == 1
    assert indexer.jobs[0][0]["filename"] == "hello.txt"
    assert any(ev.type == "indexer.submitted" for ev in job.events)


def test_create_ingestion_empty_payload_fails():
    tenant_id = "t-1"
    repo = InMemoryIngestionRepo()
    blob = FakeBlob()
    meta = FakeMeta()
    indexer = FakeIndexer()
    svc = IngestionService(tenant_id=tenant_id, repo=repo, blob=blob, meta=meta, indexer=indexer)

    with pytest.raises(Exception):
        svc.create_ingestion(CreateIngestionRequest())


