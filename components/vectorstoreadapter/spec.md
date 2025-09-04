# VectorStoreAdapter — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + in-memory impl + tests)

## 1) Purpose
Provide a stable **port** for vector storage and similarity search used by Indexer (write path) and SearchService (read path). Internals (Pinecone, FAISS, Weaviate, in-memory) are **adapters** that conform to the same runtime-validated contracts.

## 2) Responsibilities
- Upsert vector records (id, vector, metadata, optional text/refs) into a **namespace**.
- Query by vector, top_k, and optional metadata filter (DNF structure).
- Fetch records by ids, delete by ids or filter, and basic stats.
- Enforce schemas (Pydantic) and raise uniform, typed errors.
- Be observable: structured logs + trace hooks (placeholders present).

## 3) Consumers & Edges
- **Indexer** calls `upsert(namespace, records)` and `stats(namespace)` after indexing.
- **SearchService** calls `query(namespace, vector, top_k, filter)` and `fetch(namespace, ids)`.
- **MetadataService** _may_ read/update metadata later (stretch; not in this iteration).

### 3.1 Port (stable interface)
```py
class VectorStorePort(Protocol):
    def upsert(self, namespace: str, records: list[VectorRecord]) -> UpsertResult: ...
    def query(self, namespace: str, vector: list[float], top_k: int, flt: Optional[DNFFilter]) -> QueryResult: ...
    def fetch(self, namespace: str, ids: list[str]) -> FetchResult: ...
    def delete(self, namespace: str, ids: Optional[list[str]] = None, flt: Optional[DNFFilter] = None) -> DeleteResult: ...
    def stats(self, namespace: Optional[str] = None) -> StatsResult: ...
````

## 4) Data Contracts (summary)

* `VectorRecord`: `{ id: str, vector: list[float], metadata: dict[str, Any], text?: str, document_id?: str, chunk_id?: str }`
* `DNFFilter`: OR of AND groups; each condition is `{ field: str, op: Literal["eq","neq","gt","gte","lt","lte","in","nin","exists"], value?: Any }`
* Results: `UpsertResult, QueryResult(matches: list[QueryMatch]), FetchResult, DeleteResult, StatsResult`
* All contracts validated via Pydantic in `models.py`.

## 5) Non-goals (v0.1)

* Hybrid search (BM25 + dense) – defer.
* Sparse vectors – defer.
* Per-dimension quantization / advanced index mgmt – adapter-specific; out of port.

## 6) Observability

* Adapters log `action`, `namespace`, `count`, `top_k`, `latency_ms`.
* TODO: Add OpenTelemetry spans in Gate wrapper.

## 7) Error Policy

* Convert backend exceptions to `VectorStoreError` subclasses:

  * `NamespaceNotFound`, `BadRequest`, `BackendUnavailable`, `ConflictError`.

## 8) Testability

* In-memory adapter implements cosine similarity and metadata DNF filtering.
* Deterministic tests in `tests/vectorstoreadapter/`.

## 9) Security & Multi-Tenancy

* Namespaces are tenant-scoped by convention (e.g., `tenant_{id}__default`).
* Port doesn’t enforce auth; upstream (ApiGateway/AuthService) provides JWT and tenancy decisions.

## 10) TODO

* [ ] Add OpenTelemetry spans.
* [ ] Add FAISS adapter (local fast search).
* [ ] Batch delete by filter in Pinecone adapter when implemented.
* [ ] Add vector normalization toggle in port (per adapter capability).

````

---

```python
