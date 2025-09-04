# Indexer — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: **Testability + Observability + Swap-able internals (ports/adapters)**  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Turn raw documents (or pre-extracted text) into **retrievable, chunked, embedded** entries in a vector store with searchable metadata. Expose a stable API to create indexing jobs, stream progress, and query job status/results. Internals (chunker, embedder, vector store) are swappable behind **ports**.

## 2) Responsibilities
- Accept input documents via reference (blob URI + metadata) or pre-extracted text.
- Normalize, **chunk**, and embed content.
- **Upsert** chunks + metadata into a vector store under a tenant namespace.
- Emit progress events and persist job status (`pending -> running -> completed/failed`), partial success allowed.
- **Deduplicate** on document hash/fingerprint (if provided) and respect reindexing flags.
- Enforce per-tenant limits (size, count, concurrency) at a later stage.

## 3) External Interfaces (HTTP)
**Base path:** `/indexer`

### 3.1 POST `/indexer/jobs`
Create an indexing job.

**Request (JSON):**
```json
{
  "tenant_id": "t-123",
  "doc": {
    "doc_id": "optional-external-id",
    "blob_uri": "s3://bucket/key.pdf",
    "text": "optional raw text if already extracted",
    "fingerprint": "sha256:.... (optional)",
    "metadata": { "title": "Contract A", "tags": ["nda","2022"] }
  },
  "options": {
    "chunk_size": 800,
    "chunk_overlap": 120,
    "reindex": false,
    "vector_namespace": "docs"
  }
}
````

**Response (201):**

```json
{
  "job_id": "idx_abc123",
  "status": "pending"
}

### 3.2 GET `/indexer/jobs/{job_id}`

Return job status + summary.

```json
{
  "job_id": "idx_abc123",
  "tenant_id": "t-123",
  "status": "running",
  "created_at": "2025-09-04T12:00:00Z",
  "updated_at": "2025-09-04T12:00:06Z",
  "counts": { "chunks_total": 12, "chunks_indexed": 5, "errors": 0 },
  "errors": []
}

### 3.3 GET `/indexer/jobs/{job_id}/events`

Returns recent progress events (polling).

```json
{
  "job_id": "idx_abc123",
  "events": [
    { "ts": "...", "type": "chunked", "data": { "count": 12 } },
    { "ts": "...", "type": "embedded_batch", "data": { "from": 0, "to": 5 } },
    { "ts": "...", "type": "upserted", "data": { "count": 5 } }
  ]
}

## 4) Domain & Ports (Contracts)

* **ChunkerPort**: `(text, opts) -> list[Chunk]`
* **EmbedderPort**: `embed_texts(list[str]) -> list[list[float]]` (batched internally)
* **VectorStorePort**: `upsert(namespace, items: list[VectorItem]) -> None`
* **JobStorePort**: CRUD for jobs + events (in-memory default)
* **BlobPort** (future): if `blob_uri` provided and no `text`, fetch/extract (out-of-scope for first pass; use stub)

## 5) Observability

* Structured logging around each phase: `chunking_started`, `chunking_completed`, `embedding_started`, `embedding_completed`, `upsert_started`, `upsert_completed`, `job_completed`/`job_failed`.
* Trace ids and tenant ids included in logs.
* Progress events persisted in JobStore for polling (SSE later).

## 6) Validation & Constraints

* Require `tenant_id`.
* If neither `blob_uri` nor `text` is provided → 400.
* Enforce `chunk_size` sane bounds (min 100, max 4000).
* Normalize newlines and collapse excessive whitespace before chunking.

## 7) Failure Modes

* Partial failures allowed: failed embeds or upserts recorded; job can still `completed` with `errors > 0`.
* Vector store outages → job `failed` with retained events for troubleshooting.

## 8) Security & Multi-Tenancy

* All calls expect upstream gateway to provide a valid JWT; this component only **requires** `tenant_id` in payload for now (trust boundary to be hardened later).
* Namespace = `{tenant_id}:{options.vector_namespace or 'default'}`.

## 9) Testing Strategy

* Unit: chunker splits as expected; embedder returns stable shapes; vector store receives items; job lifecycle transitions.
* Integration (in-memory): POST job → runs synchronously (first pass) → GET job shows completed and events non-empty.
* Golden fixtures for chunking behavior.

## 10) TODO (Next Iterations)

* [ ] Add SSE streaming endpoint for live progress.
* [ ] Integrate real BlobStorageAdapter fetch & text extraction hook.
* [ ] Add dedup by fingerprint in JobStore with skip logic when `reindex=false`.
* [ ] Concurrency: offload to worker queue + idempotent retries.
* [ ] Enforce plan limits (bytes, chunks, concurrency).
* [ ] OpenTelemetry spans + trace context propagation.
* [ ] Batch size tuning + back-pressure control.

````

```python
