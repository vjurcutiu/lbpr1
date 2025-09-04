# EmbeddingAdapter — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory fake impl + tests)

## 1) Purpose
Provide a stable port for embedding text sequences into dense vectors, with swappable providers (e.g., OpenAI, local models). Expose a simple HTTP edge to be consumed by other services (Indexer, SearchService, ChatService). Maintain strict contracts and measurable behavior.

## 2) Responsibilities
- Accept standardized requests for embedding (batch texts).
- Produce deterministic, well-structured responses with metadata (dims, model, usage).
- Support normalization and optional dimensional projection (provider permitting).
- Emit logs/metrics for latency, batch size, and provider outcome.
- Be easily testable with a deterministic fake adapter.

## 3) Non-Responsibilities
- Tokenization or chunking of documents (handled upstream).
- Vector storage (handled by VectorStoreAdapter).
- Rate limiting / auth enforcement (handled by ApiGateway/AuthService). This service still validates JWT if placed behind gateway.

## 4) Edges / Ports
**Port:** `EmbeddingPort`  
- `embed(request: EmbedRequest) -> EmbedResult` (sync)  
- `aembed(request: EmbedRequest) -> EmbedResult` (async)

**HTTP Edge:** (FastAPI)
- `POST /v1/embeddings` — body: `EmbedRequestHttp`, response: `EmbedResponseHttp`

## 5) Schemas (Contracts)
- `EmbedRequest`:
  - `texts: List[str]` (non-empty, each non-empty, max total characters configurable)
  - `model: str` (e.g., "text-embedding-3-small")
  - `dimensions: Optional[int]` (provider may down-project)
  - `normalize: bool` (L2 normalize outputs)
  - `user: Optional[str]` (for provider-side tracing/abuse monitoring)
  - `truncate: Literal["NONE","START","END"]` (policy if provider requires truncation)
  - `metadata: Dict[str, Any]` (pass-through, optional)
- `EmbedResult`:
  - `vectors: List[List[float]]` (len == len(texts))
  - `model: str`
  - `dimensions: int`
  - `usage: Dict[str, int]` (e.g., {"prompt_tokens": ..., "total_tokens": ...})
  - `provider: str` (e.g., "fake", "openai")
  - `normalized: bool` (true if L2 normalization applied)

## 6) Observability
- Logs: batch size, dims, provider, latency ms, errors with error code.
- Metrics (future): histogram for latency, counter for requests/failures.

## 7) Errors
- `EmbeddingError(code, message, cause?)`
  - Codes: `INVALID_INPUT`, `PROVIDER_ERROR`, `INTERNAL_ERROR`, `CONFIG_ERROR`.

## 8) Configuration
- `EMBEDDING_PROVIDER` = `"fake"` | `"openai"`
- `EMBEDDING_DEFAULT_MODEL` (default: `"text-embedding-3-small"`)
- `EMBEDDING_MAX_TEXTS` (default: 128)
- `EMBEDDING_MAX_TOTAL_CHARS` (default: 200_000)
- Provider-specific env (e.g., `OPENAI_API_KEY`).

## 9) Testability
- Deterministic Fake adapter (hash-based) for stable tests.
- Route tests with TestClient.
- Contract tests ensuring dims, normalization, and length invariants.

## 10) TODO
- [ ] Add OpenTelemetry spans (parent span injection) and metrics exporter.
- [ ] Add provider registry file + CLI to swap.
- [ ] Add streaming embeddings (future).
- [ ] Add pinned JSON schema for requests/responses.

```python
