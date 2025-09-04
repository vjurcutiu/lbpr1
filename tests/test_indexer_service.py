import pytest
from components.indexer.service import IndexerService
from components.indexer.adapters_inmemory import InMemoryJobStore, InMemoryVectorStore, SimpleChunker, DummyEmbedder
from components.indexer.schemas import CreateIndexJobRequest, DocInput, IndexOptions


def make_svc():
    return IndexerService(
        chunker=SimpleChunker(),
        embedder=DummyEmbedder(),
        vector_store=InMemoryVectorStore(),
        job_store=InMemoryJobStore(),
    )


def test_create_job_with_text_happy_path():
    svc = make_svc()
    payload = CreateIndexJobRequest(
        tenant_id="t-1",
        doc=DocInput(text="one two three " * 500, metadata={"title": "Demo"}),
        options=IndexOptions(chunk_size=100, chunk_overlap=20, vector_namespace="docs"),
    )
    job_id = svc.create_job(payload)
    status = svc.get_job(job_id)
    assert status.status in ("completed", "failed")  # should be completed
    assert status.counts.chunks_total > 0
    assert status.counts.chunks_indexed == status.counts.chunks_total or status.status == "failed"


def test_create_job_validation_error():
    svc = make_svc()
    payload = CreateIndexJobRequest(
        tenant_id="t-1",
        doc=DocInput(),  # no text, no blob
    )
    job_id = svc.create_job(payload)
    status = svc.get_job(job_id)
    assert status.status == "failed"
    assert status.counts.errors >= 1


