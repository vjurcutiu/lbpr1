# ApiGateway Component — Contract-Driven Spec

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priority: Testability and observability first. Contract-driven development.

## 1) Purpose

A single entrypoint (HTTP/WS) that validates and routes API calls to internal services (AuthService, IngestionService, SearchService, ChatService, RateLimiter, MetadataService, VectorStoreAdapter, etc.) behind stable **contracts**. The ApiGateway enforces **authentication**, **authorization**, **rate-limits**, **UWF envelopes**, **request validation**, **response shaping**, and **observability** (logs, traces, metrics, audit events).

## 2) Responsibilities

- Expose public API (HTTP/WS) with versioned routes (`/v1/...`).
- Validate all requests using **contract models** (pydantic) & **UWF** response envelopes.
- Enforce **Auth** (JWT w/ tenant + user scopes) and **RateLimiter** policies.
- Fan-out to internal ports (adapters) via **ports.py** interfaces.
- Standardize **errors** (machine-readable, traceable) and **audit events**.
- Provide **health**, **readiness**, **version** routes.
- Emit **OpenTelemetry** spans and structured logs; attach **trace_id**, **request_id**, **tenant_id** to each log line.

## 3) Out of Scope

- Business logic of ingestion, search, chat, embeddings, storage (delegated via ports).
- Long-running tasks orchestration (delegated to WorkerManager/Task system).

## 4) Edges (Ports)

- **AuthPort**: `verify_token`, `authorize(scopes)`, returns identities & scopes.
- **RateLimiterPort**: `check(limit_key, quota)`, `consume(...)`.
- **IngestionPort**: `create_job`, `append_files`, `finalize_job`, `get_job`.
- **SearchPort**: `search(query, filters, top_k, rerank)`.
- **ChatPort**: `completion(messages, tools?, stream?)`.
- **MetadataPort**: `get_file_metadata`, `set_tags`, `get_tags`.

_All ports return typed results or raise typed errors from `errors.py`._

## 5) UWF (Unified Wire Format)

All responses are shaped as:

```json
{
  "ok": true,
  "result": { ... },
  "error": null,
  "meta": {
    "trace_id": "string",
    "request_id": "string",
    "tenant_id": "string|null",
    "duration_ms": 12
  }
}
On failure:

json
Copy code
{
  "ok": false,
  "result": null,
  "error": {
    "type": "AUTH_ERROR|RATE_LIMIT|VALIDATION|NOT_FOUND|CONFLICT|UPSTREAM|INTERNAL",
    "code": "string-machine-code",
    "message": "human readable",
    "details": { "any": "structured details" }
  },
  "meta": { ...same as above... }
}
6) Routes (v1)
GET /v1/health → {status, version, time}

GET /v1/ready → readiness probe

POST /v1/ingestions → create ingestion job

POST /v1/ingestions/{job_id}/files → append files by reference (URIs) or upload tokens (blob adapter handles actual storage)

POST /v1/ingestions/{job_id}/finalize → finalize/commit job

GET /v1/ingestions/{job_id} → job status

POST /v1/search → vector/keyword search w/ filters

POST /v1/chat/completions → chat turn; optional streaming (SSE/WS reserved)

GET /v1/files/{file_id}/metadata → fetch metadata

POST /v1/files/{file_id}/tags → set tags

All endpoints require Authorization: Bearer <jwt> except health/ready.

7) Observability
Request/Response logging with trace_id, request_id, tenant_id, route, status, duration_ms.

OTel spans: apigw.request, child spans per port call (auth.verify, rl.check, ingest.create_job, etc.).

Metrics: request count & latency histograms by route/result; rate-limit rejections; auth failures.

Audit events (info level): authentication outcome, ingestion created/finalized, search executed, chat requested.

8) Testability
All handlers accept ports via dependency injection; tests can inject fakes.

Route tests (pytest + httpx TestClient) with golden request/response fixtures.

Contract tests enforce schema invariants and UWF envelope shape.

Error-path tests: auth fail, rate-limit fail, validation fail, upstream fail.

9) Security & Multi-Tenancy
Mandatory JWT with tenant_id, user_id, scopes.

Per-tenant rate limits and size limits (body size, files per job).

No cross-tenant leakage; IDs are validated against tenant_id.

Input hard limits & payload size enforcement at app/middleware level.

10) TODO (Spec Evolution)
 Add WS/SSE streaming for /v1/chat/completions partial tokens.

 Add pagination & cursors for search results.

 Hook into centralized audit sink (Kafka or DB).

 Add request body max size & multipart upload path.

 Add structured filter grammar (DNF) alignment with SearchService.