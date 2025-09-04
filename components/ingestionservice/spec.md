# IngestionService — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Accept raw files or references, persist them via a BlobStorageAdapter, register file metadata, and submit indexing jobs to the Indexer component. Surfaces ingestion job lifecycle with progress and events for observability.

## 2) Responsibilities
- Validate incoming ingestion payloads (files-bytes, file refs, or URLs).
- Persist files (via BlobStorageAdapter) and produce stable blob URIs.
- Upsert basic metadata (via MetadataService).
- Create an indexing job per file set (via Indexer).
- Track job state (PENDING → RUNNING → SUBMITTED_TO_INDEXER → COMPLETED/FAILED).
- Emit progress + audit events (append-only).
- Expose HTTP API to create jobs and query status/events.

## 3) Non-Responsibilities
- Chunking/embedding/upserting to vector DB (Indexer handles this).
- Full auth; assume request already has valid tenant/user claims (AuthService).
- Long-running workers; initially synchronous orchestration (later: async).

## 4) Contracts (summary)
- `CreateIngestionRequest { files?: [InlineFile], file_refs?: [FileRef], source_urls?: [HttpUrl] }`
- `InlineFile { filename, bytes_b64, content_type }`
- `FileRef { filename, blob_uri, content_type }`
- `CreateIngestionResponse { job: IngestionJob }`
- `IngestionJob { id, tenant_id, status, created_at, updated_at, items: [IngestionItem], index_job_id? }`
- Status enum: PENDING, RUNNING, SUBMITTED_TO_INDEXER, COMPLETED, FAILED
- Events: type, message, ts, data (JSON)

Ports:
- `BlobStorageAdapterPort.put_bytes(tenant_id, path_hint, bytes, content_type) -> blob_uri`
- `MetadataServicePort.upsert_file(tenant_id, blob_uri, filename, content_type, size_bytes, extra?) -> file_id`
- `IndexerPort.create_job(tenant_id, items: [IndexInputItem]) -> index_job_id`

## 5) HTTP Edges
- `POST /ingestions` → CreateIngestionResponse
- `GET /ingestions/{job_id}` → IngestionJob
- `GET /ingestions/{job_id}/events` → { events: [IngestionEvent] }

## 6) Data & Persistence
- In-memory repository for v0.1 (Job + Events). Replace with DB later via repository port.

## 7) Observability
- Emit append-only events with UWF-ish envelope (type, message, data).
- Include timestamps and status transitions.

## 8) Failure Modes
- Blob put failure → mark job FAILED, emit event.
- Metadata upsert failure → FAILED.
- Indexer submission failure → FAILED.
- Partial success: keep per-item states; job fails if *any* critical step fails (v0.1). (TODO: support partial completions.)

## 9) Security & Multi-Tenancy
- All calls require AuthService JWT; `tenant_id` must be present in context. (For tests we inject tenant_id.)
- Enforce tenant isolation at repo layer.

## 10) TODOs (next iterations)
- [ ] Add background task queue (Huey/Redis or PG-backed).
- [ ] Stream events over Server-Sent Events (SSE) / WebSocket.
- [ ] Enforce plan limits (max files, size caps).
- [ ] Add dedup by content hash and re-index policy.
- [ ] Persist to Postgres with SQLAlchemy repo.
- [ ] Add OpenTelemetry spans across ports.

```python
