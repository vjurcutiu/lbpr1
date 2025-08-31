# ./specs/components/apigateway.md
# Component: ApiGateway

## 1) Purpose
The ApiGateway is the single public entrypoint for the remote FastAPI server. It exposes a stable HTTP surface for clients (desktop app, CLI, partner systems) and brokers calls to internal services (AuthService, ChatService, SearchService, IngestionService, MetadataService, RateLimiter middleware, etc.). It enforces **contracts**, **authentication/authorization**, **rate limits**, **observability**, and **error normalization** while remaining agnostic to internal implementations.

## 2) Responsibilities
- Terminate HTTP(S), manage CORS, pagination, and versioned routes (`/v1`).
- Validate requests/responses against Pydantic/JSON-Schema contracts (UWF envelope).
- Verify JWTs (via AuthService introspection or locally cached JWKS).
- Enforce rate limiting (token-bucket) at tenant + user scopes.
- Attach tracing/metrics/logs (OpenTelemetry), propagate correlation IDs.
- Translate internal error types to public error codes.
- Provide health, readiness, and version endpoints.

Non-Responsibilities:
- No business logic (chat/search/ingestion/metadata) beyond orchestration & validation.
- No direct DB access; all data comes from internal services through well-defined ports.

## 3) Contracts (UWF: Unified Wire Format)
All requests & responses use a standard envelope:

```json
{
  "uwf_version": "1.0",
  "kind": "command|query",
  "trace_id": "uuid",
  "tenant_id": "string",
  "actor": {"user_id": "string", "scopes": ["..."]},
  "ts": "RFC3339",
  "payload": { "...contract-specific..." },
  "meta": { "client": "lbp3-desktop", "app_version": "..." }
}
Error envelope:

json
Copy code
{
  "uwf_version": "1.0",
  "error": {
    "code": "APIGW_xxx",
    "message": "human-readable",
    "details": { "field": "..." }
  },
  "trace_id": "uuid",
  "ts": "RFC3339"
}
3.1 Endpoint Contracts (selected v1 set)
POST /v1/chat/ask

kind: command

payload: { "conversation_id": "str|null", "message": "str", "stream": "bool", "context": {"top_k": int, "filters": {...}} }

response (non-stream): { "answer": "str", "citations": [ { "doc_id": "str", "snippet": "str", "score": float } ], "conversation_id": "str" }

response (SSE/WS deferred): handled by ChatService, ApiGateway returns 202 + stream upgrade or channel token.

POST /v1/search/query

kind: query

payload: { "query": "str", "top_k": int, "filters": {...}, "fusion": "rrf|zscore" }

response: { "results": [ { "doc_id": "str", "title": "str", "snippet": "str", "score": float } ], "latency_ms": int }

POST /v1/ingest/init

kind: command

payload: { "files": [ { "name": "str", "size": int, "mime": "str" } ], "strategy": "sync|async" }

response: { "ingestion_id": "str", "upload_urls": [ { "name":"str","url":"str","headers":{}} ] }

POST /v1/ingest/commit

payload: { "ingestion_id": "str" }

response: { "ingestion_id": "str", "status": "queued|processing|done", "files_total": int }

GET /v1/metadata/{doc_id}

response: { "doc_id":"str", "metadata": { ... }, "hash":"str" }

GET /v1/healthz, GET /v1/readyz, GET /v1/version (plain JSON).

All use the UWF envelope in request/response bodies except simple health/version.

4) Edges (Ports) & Dependencies
AuthServicePort: verify JWT / introspect, fetch JWKS, check scopes.

RateLimiterPort: token-bucket check (keyed by tenant_id + user_id + route).

ChatServicePort: ask(); supports stream or non-stream paths.

SearchServicePort: query().

IngestionServicePort: init_ingestion(), commit().

MetadataServicePort: get_document_metadata(doc_id).

5) Security & Multitenancy
Require JWT with tenant_id, user_id, scopes.

Object-level isolation delegated to downstream services; ApiGateway validates tenant headers and forbids cross-tenant leakage.

Plan tier awareness for request size/limits (checked via RateLimiterPort / plan config).

6) Rate Limiting
Strategy: token-bucket (burst + refill per second). Enforced pre-handler.

Keys: {tenant}:{user}:{route} with global tenant fallback.

Over-limit -> 429 with APIGW_RATE_LIMITED.

7) Observability
OpenTelemetry tracing: one entry span per request, propagate traceparent.

Metrics: request_count, request_latency, error_count, rate_limit_hits.

Logs: structured JSON (trace_id, tenant_id, route, status, dur_ms).

Correlation: X-Request-ID (or generated) echoed back.

8) Error Model (public)
APIGW_BAD_REQUEST (400)

APIGW_UNAUTHORIZED (401)

APIGW_FORBIDDEN (403)

APIGW_RATE_LIMITED (429)

APIGW_UPSTREAM_TIMEOUT (504)

APIGW_UPSTREAM_ERROR (502)

APIGW_CONTRACT_VIOLATION (422)

APIGW_INTERNAL (500)

9) Testability
Contract tests for all DTOs (Pydantic schema roundtrip, golden JSON).

Route tests via FastAPI TestClient (success + error + rate limit).

Port fakes for deterministic upstream behavior.

Trace/log assertions via captured handlers.

10) Deployment & Config
ENV: APIGW_PORT, CORS_ORIGINS, JWKS_URL or Auth introspection URL, RATE_LIMIT_*.

Run behind reverse proxy (Kong) but independently testable.

11) TODO (next passes)
Add SSE/WS streaming contract for /v1/chat/ask?stream=true.

Add pagination contract helpers.

Add request size limits per plan (middleware).

Wire concrete port adapters (HTTP clients) and resiliency (timeouts, retries, circuit-breakers).

Add route-level authorization matrix (scope → route map).