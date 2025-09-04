# AuthService — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide authentication & authorization for the platform with:
- Login with credentials -> short-lived access token + long-lived refresh token.
- Token verification (tenant isolation + user scopes).
- Token refresh flow.
- Dependency helpers for FastAPI routes (require scopes).
- Pluggable crypto & user store (HS256 by default, RS256/JWKS later).

## 2) Responsibilities
- Validate credentials using a **UserRepoPort** (contract).
- Issue/verify JWTs using a **TokenSignerPort** (contract).
- Enforce **tenant_id** + **scopes** on protected endpoints.
- Support **key rotation** via `kid` header (contract on signer).
- Provide HTTP routes: `/auth/login`, `/auth/refresh`, `/auth/me`.
- Provide `require_scopes([...])` dependency for other services.

## 3) Non-Responsibilities
- User registration / password reset flows. (Separate component.)
- Rate limiting. (Handled by RateLimiter.)
- Audit logging storage. (Emit events/logs; storage belongs elsewhere.)

## 4) Contracts / Edges
- `TokenSignerPort`: `sign`, `verify`, `active_kid`, `list_kids`.
- `UserRepoPort`: `get_user_by_credentials`, `get_user_by_id`.
- `ClockPort` (optional): time source for testability.
- HTTP Edges (FastAPI router):
  - `POST /auth/login` -> `UWFResponse<tokens>`
  - `POST /auth/refresh` -> `UWFResponse<tokens>`
  - `GET /auth/me` -> `UWFResponse<user>`
- Dependencies:
  - `require_scopes(scopes: list[str])` -> raises on missing/invalid.

## 5) Data Models (logical)
- **AccessTokenClaims:** `sub, tenant_id, scopes, iat, exp, jti, kid`.
- **RefreshTokenClaims:** `sub, tenant_id, typ="refresh", iat, exp, jti, kid`.
- **IssuedTokens:** `access_token, refresh_token, token_type="Bearer", expires_in`.
- **User:** `id, email, display_name, tenant_id, is_active, scopes`.

## 6) Security & Multi-Tenancy
- Each token carries `tenant_id` and `scopes`.
- Scope checks enforce least privilege (e.g., `documents:ingest`, `chat:read`).
- Tenants are isolated at the token and data access layers.

## 7) Observability
- Structured logs on login/refresh/verification (with trace_id if present).
- Error codes in UWF: AUTH_ERROR, VALIDATION, NOT_FOUND, CONFLICT, INTERNAL.

## 8) Config (env)
- `AUTH_ALG` = `HS256` (default) | `RS256` (future)
- `AUTH_SECRET` = required for HS256
- `ACCESS_TTL_SECONDS` = e.g., 900 (15m)
- `REFRESH_TTL_SECONDS` = e.g., 1209600 (14d)
- `AUTH_ISSUER` = `lbp3-rs`
- `AUTH_AUDIENCE` = `lbp3-clients`

## 9) Testability
- In-memory `UserRepoPort` for tests.
- Deterministic ClockPort in tests.
- Pure funcs where practical; small, explicit adapters.

## 10) TODO (Next Iterations)
- [ ] Add RS256 signer + `.well-known/jwks.json` proper JWKS.
- [ ] Add token revocation (deny-list) + rotation grace windows.
- [ ] Add OpenTelemetry spans + structured event emission.
- [ ] Persist user repo (SQL) + password hashing adapter.
- [ ] Stronger password policy & login attempt throttling hooks.
- [ ] Add `scope wildcards` (e.g., `documents:*`) + hierarchical checks.