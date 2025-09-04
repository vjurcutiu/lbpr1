import math
import time
import uuid
from typing import List, Optional, Sequence

from .contracts import (
    EmbeddingAdapterPort,
    Filter,
    Fusion,
    SearchRequest,
    SearchResponse,
    SearchHit,
    VectorHits,
    VectorStoreAdapterPort,
)


def _zscore_fusion(vscores: List[float]) -> List[float]:
    if not vscores:
        return vscores
    mean = sum(vscores) / len(vscores)
    var = sum((s - mean) ** 2 for s in vscores) / max(1, (len(vscores) - 1))
    sd = math.sqrt(var) if var > 0 else 1.0
    return [(s - mean) / sd for s in vscores]


async def execute_search(
    tenant_id: str,
    req: SearchRequest,
    embedding: Optional[EmbeddingAdapterPort],
    vector_store: VectorStoreAdapterPort,
) -> SearchResponse:
    """
    Orchestrates a search:
      - embed query if semantic or hybrid
      - query vector store
      - (future) if hybrid, also query keyword store & fuse results
    """
    t0 = time.perf_counter_ns()
    vector: Optional[List[float]] = None

    if req.search_type in ("semantic", "hybrid") and req.query:
        if embedding is None:
            raise RuntimeError("Embedding adapter not configured.")
        vector = await embedding.embed_query(req.query)

    # v0.1: Only vector search. (hybrid hooks left for future keyword adapter.)
    vhits: VectorHits = await vector_store.query(
        tenant_id=tenant_id,
        vector=vector,
        top_k=req.top_k,
        offset=req.offset,
        filters=req.filters,
        include_snippets=req.include_snippets,
        snippet_max_chars=req.snippet_max_chars,
        metadata_fields=req.metadata_fields,
    )

    # If hybrid with future keyword path, apply fusion here.
    # For now, just return vhits as-is.
    hits = [
        SearchHit(
            doc_id=h.doc_id,
            score=float(h.score),
            metadata={k: v for k, v in (h.metadata or {}).items() if (not req.metadata_fields or k in req.metadata_fields)},
            snippet=h.snippet,
        )
        for h in vhits.hits
    ]

    took_ms = int((time.perf_counter_ns() - t0) / 1_000_000)
    return SearchResponse(
        query_id=str(uuid.uuid4()),
        took_ms=took_ms,
        total=vhits.total,
        hits=hits,
    )

---

```python
