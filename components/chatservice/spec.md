# ChatService — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide authenticated chat sessions with message history, assistant replies (via LLMAdapter), optional RAG context (via SearchService/VectorStoreAdapter), lightweight message metadata, and streaming hooks. All internals sit behind ports so the LLM, memory store, and retrieval strategy can be swapped without breaking edges.

## 2) Responsibilities
- Create/read/update chat sessions (title, status, tenant, participants).
- Append messages (user/tool/assistant), maintain ordering and metadata.
- Invoke LLMAdapter for assistant responses (sync for v0.1; streaming hook defined in contract).
- Optional retrieval step (pluggable) before LLM call: attach `citations`/`context`.
- Emit progress & span events for observability (OpenTelemetry spans + structured logs).
- Enforce tenant isolation & scope checks via AuthService (token parsed upstream; contract includes tenant id on calls).

## 3) Non-Responsibilities
- Authentication/JWT validation (handled by AuthService/middleware).
- Blob/file storage (BlobStorageAdapter).
- Vector store internals (VectorStoreAdapter).  
- Billing/quotas (RateLimiter/Billing components).

## 4) Domain Terms
- **Chat**: container of ordered messages and metadata.  
- **Message**: user, assistant, or tool output; can include `context_snippets` and `citations`.  
- **Turn**: user message followed by zero or more assistant/tool messages.

## 5) Ports (contracts)
- `IChatService`: primary application port (create session, list, get, post message, stream).  
- `ILLMAdapter`: called to generate assistant content from prompt + context.  
- `IRetrievalAdapter` (optional): given a query & tenant, returns snippets/citations.

## 6) Edge API (HTTP/WS)
- `POST /chats` → Create chat (title optional).  
- `GET /chats/{chat_id}` → Chat details + last N messages (param `limit`).  
- `GET /chats` → List chats (pagination: `cursor`, `limit`).  
- `GET /chats/{chat_id}/messages` → List messages (`cursor`, `limit`, `order=asc|desc`).  
- `POST /chats/{chat_id}/messages` → Append a user message and request assistant reply (`stream=false` for v0.1 sync).  
- (Hook for v0.2) `GET /chats/{chat_id}/stream` (SSE/WS): progress + tokens.

Request/response envelopes follow UWF-style JSON with `ok`, `error`, and `data`. See `contracts.py`.

## 7) Data Model (simplified v0.1)
Chat:
- `id: str`
- `tenant_id: str`
- `title: str`
- `status: enum['active','archived']`
- `created_at, updated_at: datetime`

Message:
- `id: str`
- `chat_id: str`
- `role: enum['user','assistant','tool']`
- `content: str`
- `metadata: dict[str, Any]` (optional)
- `citations: list[Citation]` (optional)
- `created_at: datetime`

Citation:
- `source_id: str`
- `title: str | None`
- `score: float | None`
- `uri: str | None`

## 8) Observability
- Spans: `chat.create`, `chat.list`, `chat.get`, `chat.messages.list`, `chat.messages.create`, `chat.generate`.
- Attributes: `tenant_id`, `chat_id`, `message_id`, `llm.provider`, `retrieval.enabled`.
- Logs: Structured json lines with same keys. Errors map to typed `ChatError`.

## 9) Error Policy
- `ChatNotFound`, `MessageNotFound`
- `Forbidden` (tenant mismatch)
- `InvalidInput`
- `UpstreamError` (LLM/retrieval)
- Map to HTTP: 404/403/400/502. Responses never leak internals.

## 10) Testability
- In-memory store + fake LLM adapter (deterministic) in tests.
- Golden fixtures for envelopes.
- Contract tests for port + edge tests for HTTP.

## 11) TODO (next iterations)
- [ ] Implement SSE/WS token streaming.
- [ ] Plug `IRetrievalAdapter` (RAG) with feature flag.
- [ ] Add pagination cursors (opaque) for lists.
- [ ] Add title auto-generation on first turn (background-safe hook).
- [ ] Add soft delete/archival + search by title.
- [ ] Add rate limiting & quotas integration.
- [ ] Persist to DB (Postgres) with repository port + migrations.

---

```python
