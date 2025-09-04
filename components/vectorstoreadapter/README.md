# VectorStoreAdapter

Contract-driven vector storage/search port with pluggable adapters.

## Adapters
- `InMemoryVectorStore`: deterministic, test-friendly, cosine similarity + DNF filters.
- `PineconeVectorStore`: stub (wire later).

## Quickstart (tests)
See `tests/vectorstoreadapter/` for usage.

---

```python
