# RateLimiter — Contract-Driven Spec (v0.1)
#
# Project: lbp3-rs (FastAPI remote server for a RAG chat app)
# Priorities: Testability + Observability + Swap-able internals (ports/adapters)
# Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide request throttling/quotas for API consumers (per-IP, per-user, per-tenant, global) using configurable policies. Designed to be used:
- (a) as an ASGI middleware in our FastAPI apps, and/or
- (b) as a small service/router exposing explicit “check/consume/reset” edges for other services.

## 2) Responsibilities
- Enforce rate limits via standard algorithms:
  - Token Bucket (default): bursty traffic with sustained rate.
  - Leaky Bucket (optional path): steady drain, queue semantics (first version: simple reject on overflow).
- Policy targeting & keying strategies:
  - key scopes: ip | user | tenant | global | custom
  - matchers by method + path (regex) with priority/first-match semantics.
- Return standard rate-limit headers:
  - `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` (on 429).
- Safe to run in single-process (in-memory store) and multi-process (future Redis adapter).
- Telemetry: OTel spans/attributes for decisions (allow/deny), counters/timers for cost, wait, retries.
- Testability: deterministic time via injected time provider; in-memory store for unit tests.

## 3) Edges (HTTP/ASGI)
### 3.1 ASGI Middleware (primary usage)
- Applies configured policies to incoming requests.
- Builds a limit key based on configured scope:
  - ip: `client.host`
  - user: `X-User-Id` header (placeholder until AuthService integration)
  - tenant: `X-Tenant-Id` header
  - global: constant
  - custom: optional callable hook
- On allow: attach headers (limit/remaining/reset).
- On deny: return 429 JSON `{ "error": "rate_limited", "retry_after": <seconds> }` with headers.

### 3.2 Router (service surface)
- `POST /ratelimiter/consume` — body: { key, policy, cost? } → { allowed, remaining, retry_after? }
- `GET  /ratelimiter/quota/{key}` — inspect current counters for debugging/ops
- `POST /ratelimiter/reset` — body: { key } → reset state (ops convenience)

> Note: Router is optional; middleware is the standard integration in other components like ApiGateway.

## 4) Contracts (Ports/DTOs)
- `Policy`:
  - `name: str`
  - `algorithm: Literal["token_bucket","leaky_bucket"]` (default token)
  - `rate: int` (tokens per period)
  - `period: int` (seconds for the rate window)
  - `burst: int` (max tokens in bucket)
  - `scope: Literal["ip","user","tenant","global","custom"]`
  - `path_pattern: str` (regex)
  - `methods: list[str] | None` (if None, all)
  - `cost: int = 1` (default cost per request)
  - `metadata: dict[str, Any] = {}` (future: plan tier, notes)
- `ConsumeRequest` / `ConsumeResult` (for the router)
- Port: `StateStore` with minimal atomic ops for concurrency (in-mem impl now, Redis later)
  - get(key) → value
  - set(key, value)
  - update(key, fn) → atomic compute-and-set (lock-guarded in memory; script in Redis later)

## 5) Internals
- Token Bucket state per key: `{ tokens: float, last_refill_ts: float }`
- Refill on each consume: 