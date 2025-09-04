# SearchService — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide a stable API to retrieve relevant documents/snippets from the vector store (and optionally keyword store) with filterable metadata and optional simple fusion. Contracts shield internals: we can swap vector/keyword/reranker providers without changing edges.

## 2) Responsibilities
- Accept search queries with:
  - query text (optional for pure filter queries)
  - top_k, offset
  - search_type: `semantic | keyword | hybrid`
  - fusion: `rrf | zscore` (for hybrid), optional
  - metadata filters in DNF style (must / should / must_not)
  - snippet options (return fields, windowing)
- Call EmbeddingAdapter (when needed) to embed queries.
- Call VectorStoreAdapter (and optional KeywordAdapter in future) to retrieve candidates.
- Apply simple fusion (if hybrid).
- Enforce tenant isolation (AuthService-provided tenant claims).
- Return normalized results with scores, ids, and selected metadata.
- Emit structured logs + tracing spans; expose health endpoint.

## 3) Non-Goals (v0.1)
- No external reranker (BM25/LLM rerank) yet; surface an extension point.
- No streaming results; return a single response payload.
- No pagination tokens (simple offset + limit only).

## 4) Edges / HTTP API (UWF-lite)
### POST /search
Request (JSON):
```json
{
  "query": "string",
  "top_k": 10,
  "offset": 0,
  "search_type": "semantic | keyword | hybrid",
  "fusion": "rrf | zscore | null",
  "filters": {
    "must": [{"field":"tags","op":"in","value":["contract","ruling"]}],
    "should": [],
    "must_not": []
  },
  "include_snippets": true,
  "snippet_max_chars": 240,
  "metadata_fields": ["title","path","tags"]
}
````

Response:

```json
{
  "query_id": "uuid",
  "took_ms": 12,
  "total": 123,
  "hits": [
    {
      "doc_id": "abc123",
      "score": 0.83,
      "metadata": {"title":"...", "path":"...", "tags":["..."]},
      "snippet": "..."
    }
  ]
}

### GET /search/health

* Returns `{ "status": "ok" }` if adapters are reachable.

## 5) Contracts

* Request/Response models (Pydantic)
* Ports:

  * `EmbeddingAdapterPort.embed_query(text) -> list[float]`
  * `VectorStoreAdapterPort.query(tenant_id, vector, top_k, filters) -> VectorHits`
* Domain:

  * Filter DNF (must/should/must\_not) and simple evaluators for in-memory store.
* Errors: `SearchError`, `AdapterError`, `UnauthorizedError`, `ValidationError`

## 6) Observability

* Add request\_id (UUID) per call, include in logs + response.
* Basic timings (monotonic\_ns) → took\_ms.
* Tracing hooks (no-op in v0.1; spans named `search.execute`).

## 7) Security & Multi-Tenancy

* Require AuthService JWT in production; v0.1 allows `X-Debug-Bypass-Auth: 1` for tests.
* All queries scoped by tenant\_id claim.

## 8) Testability

* Provide in-memory Embedding + Vector adapters with deterministic behavior for tests.
* Unit tests for:

  * semantic search returns expected order
  * filters (must / must\_not)
  * hybrid fusion (RRR/Z-score) happy path
  * health endpoint
  * auth bypass for tests

## 9) TODO (next iterations)

* Add BM25/keyword adapter and real hybrid fusion across both retrievers.
* Add re-ranking port (LLM or learned ranker).
* Add pagination tokens & streaming search.
* Add tracing via OpenTelemetry and metrics counters.
* Add per-plan limits (max top\_k, fields allowlist).
* Add query logging to an Analytics/Events sink.

````

---

```python
