# MetadataService — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Produce and persist document metadata for downstream RAG components. Accepts raw text or a blob reference, performs lightweight extraction (title, language guess, stats, keywords) and (optionally) advanced extraction via an LLMAdapter (summary, categories, custom fields). Exposes a stable HTTP API and domain contracts so internals (keyword extractor, LLM provider, metadata store, blob fetcher) are swappable.

## 2) Responsibilities
- Normalize inputs (text or blob reference) into a unified content payload.
- Compute **core metadata**: hash, size, mime (best-effort), charset, char/word counts, reading time, line count, created_at/ingested_at.
- Derive **semantic metadata**: title guess, language guess (best-effort), top keywords (stopword-filter + frequency), short description (optional).
- Optional: delegate **advanced extraction** to LLMAdapter (summary, categories, custom schema fields).
- Persist metadata via MetadataStore port; return a stable UWF-style response envelope with traceable IDs.
- Emit progress/logs and surface errors with stable error codes.

## 3) Non-Goals
- Heavyweight NLP (NER, NEL) in v0.1.
- OCR / PDF parsing — assumed upstream.
- Direct vectorization/embedding — belongs to Indexer/EmbeddingAdapter.

## 4) Inputs / Outputs

### 4.1 Input Types
- **Inline text**: `{ "kind": "text", "text": "...", "source_id": "optional-external-id" }`
- **Blob reference**: `{ "kind": "blob", "blob_uri": "scheme://bucket/key", "source_id": "optional-external-id" }` (resolved via BlobStorageAdapter)

### 4.2 Options
- `llm.enabled: bool` — when true, request summary/categories via LLMAdapter.
- `keyword.top_k: int` — number of keywords to return (default 10).
- `store.persist: bool` — whether to upsert into the MetadataStore (default true).
- `tenant_id: str` — tenant isolation key, required by API.

### 4.3 Output Envelope (UWF-ish)
```json
{
  "ok": true,
  "error": null,
  "data": {
    "metadata_id": "uuid",
    "tenant_id": "t1",
    "source_id": "doc-123",
    "hash_sha256": "…",
    "size_bytes": 123,
    "mime_guess": "text/plain",
    "language_guess": "en",
    "title": "First line, trimmed",
    "stats": { "chars": 1000, "words": 180, "lines": 20, "reading_time_ms": 54000 },
    "keywords": ["alpha","beta", "..."],
    "summary": "optional",
    "categories": ["optional"],
    "created_at": "iso",
    "ingested_at": "iso"
  }
}
````

## 5) HTTP Edges (FastAPI)

* `POST /metadata/extract` — Synchronous extraction.

  * Request: `ExtractRequest` (contracts)
  * Response: `Envelope[ExtractResponse]`
* `GET /metadata/{metadata_id}` — Retrieve stored record (if persisted).

  * Response: `Envelope[MetadataRecord]`

Auth: Requires AuthService JWT with tenant + user scopes: `documents:metadata`. (Stubbed for v0.1 — expect dependency injection later.)

## 6) Ports / Contracts

* `BlobReaderPort` — fetch raw bytes from a `blob_uri`.
* `LLMAdapterPort` — optional advanced extraction (summary/categories/custom).
* `MetadataStorePort` — upsert and fetch metadata records.
* `KeywordExtractorPort` — pluggable keyword extraction strategy.

Each port defined as an abstract protocol (pydantic-friendly I/O models in `contracts.py`).

## 7) Observability

* Structured logs with `component=MetadataService`, correlation ids, and timings.
* OpenTelemetry spans (if available) around high-level ops (`extract`, `persist`, `llm_summarize`).
* Return `trace_id` in response headers (TODO in v0.2).

## 8) Errors

* `metadata.invalid_input`
* `metadata.blob_not_found`
* `metadata.llm_failed`
* `metadata.store_failed`
* `metadata.internal_error`

All surfaced via envelope `{ ok:false, error:{ code, message, details } }` with HTTP 400/404/500.

## 9) Testability

* In-memory store and blob reader for unit tests.
* Pure functions for text stats + keywords.
* FastAPI router test via TestClient.

## 10) TODO (Future Iterations)

* [ ] Add language detection via fasttext or langid (optional dependency).
* [ ] Add MIME detection via `python-magic` (optional).
* [ ] Add configurable stopwords per language.
* [ ] Add trace\_id propagation to envelope and headers.
* [ ] Wire real adapters: BlobStorageAdapter, LLMAdapter, Postgres metadata store.
* [ ] Add JSON Schema for request/response; validate at edge.
* [ ] Add rate limiting + auth dependency.

````

---

```python
