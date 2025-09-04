from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .contracts import (
    EmbeddingAdapterPort,
    Filter,
    FilterCondition,
    Op,
    VectorHit,
    VectorHits,
    VectorStoreAdapterPort,
)


def _hash_to_unit_vector(text: str, dims: int = 16) -> List[float]:
    """Deterministic embedding: split sha256 into dims chunks."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # 32 bytes → map into dims floats
    vals = [int.from_bytes(h[i:i+2], "big") for i in range(0, min(32, 2 * dims), 2)]
    # pad if needed
    while len(vals) < dims:
        vals.append(0)
    # normalize
    total = sum(vals) or 1
    vec = [v / total for v in vals[:dims]]
    return vec


class InMemoryEmbeddingAdapter(EmbeddingAdapterPort):
    async def embed_query(self, text: str) -> List[float]:
        return _hash_to_unit_vector(text, 16)


@dataclass
class _Doc:
    id: str
    tenant_id: str
    vector: List[float]
    metadata: Dict[str, Any]
    text: str


def _cosine(a: List[float], b: List[float]) -> float:
    num = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)) or 1.0
    db = math.sqrt(sum(y*y for y in b)) or 1.0
    return num / (da * db)


def _passes(cond: FilterCondition, md: Dict[str, Any]) -> bool:
    val = md.get(cond.field)
    if cond.op == Op.eq:
        return val == cond.value
    if cond.op == Op.ne:
        return val != cond.value
    if cond.op == Op.lt:
        try:
            return val < cond.value
        except Exception:
            return False
    if cond.op == Op.lte:
        try:
            return val <= cond.value
        except Exception:
            return False
    if cond.op == Op.gt:
        try:
            return val > cond.value
        except Exception:
            return False
    if cond.op == Op.gte:
        try:
            return val >= cond.value
        except Exception:
            return False
    if cond.op == Op.contains:
        try:
            return cond.value in val
        except Exception:
            return False
    if cond.op == Op.in_:
        try:
            return val in cond.value
        except Exception:
            return False
    if cond.op == Op.nin:
        try:
            return val not in cond.value
        except Exception:
            return False
    return True


def _apply_filter(md: Dict[str, Any], flt: Filter) -> bool:
    # must
    if any(not _passes(c, md) for c in flt.must):
        return False
    # must_not
    if any(_passes(c, md) for c in flt.must_not):
        return False
    # should improves ranking; here we don't boost but require at least 1 if provided
    if flt.should:
        return any(_passes(c, md) for c in flt.should)
    return True


class InMemoryVectorStoreAdapter(VectorStoreAdapterPort):
    def __init__(self, docs: List[_Doc]):
        self._docs = docs

    @classmethod
    def bootstrap_sample(cls) -> "InMemoryVectorStoreAdapter":
        rng = random.Random(1337)
        docs: List[_Doc] = []
        tenants = ["test-tenant", "alpha", "beta"]
        corpus = [
            ("docA", "Contract law basics and precedents.", {"title": "Contract Law 101", "tags": ["contract","law"], "path": "/a"}),
            ("docB", "Criminal law overview and notable cases.", {"title": "Criminal Law", "tags": ["criminal","law"], "path": "/b"}),
            ("docC", "Tort law: negligence and liability discussion.", {"title": "Tort Law", "tags": ["tort","law"], "path": "/c"}),
            ("docD", "Civil procedure rules and motions.", {"title": "Civil Procedure", "tags": ["civil","procedure"], "path": "/d"}),
            ("docE", "Case study: contract breach remedies.", {"title": "Breach Remedies", "tags": ["contract","case"], "path": "/e"}),
        ]
        for i, (did, text, md) in enumerate(corpus):
            tenant_id = tenants[0]  # keep all in test-tenant for tests
            vec = _hash_to_unit_vector(text)
            docs.append(_Doc(id=did, tenant_id=tenant_id, vector=vec, metadata=md, text=text))
        return cls(docs)

    def count_documents(self) -> int:
        return len(self._docs)

    async def query(
        self,
        tenant_id: str,
        vector: Optional[List[float]],
        top_k: int,
        offset: int,
        filters: Filter,
        include_snippets: bool,
        snippet_max_chars: int,
        metadata_fields: Sequence[str],
    ) -> VectorHits:
        # filter by tenant
        pool = [d for d in self._docs if d.tenant_id == tenant_id and _apply_filter(d.metadata, filters)]
        if vector is None:
            # Pure filter search; score = 0; stable order
            ranked = [(0.0, d) for d in pool]
        else:
            ranked = [(_cosine(vector, d.vector), d) for d in pool]
            ranked.sort(key=lambda t: t[0], reverse=True)
        total = len(ranked)
        window = ranked[offset : offset + top_k]
        hits = []
        for score, d in window:
            snippet = d.text[:snippet_max_chars] if include_snippets else None
            md = d.metadata.copy()
            if metadata_fields:
                md = {k: v for k, v in md.items() if k in metadata_fields}
            hits.append(VectorHit(doc_id=d.id, score=float(score), metadata=md, snippet=snippet))
        return VectorHits(total=total, hits=hits)

---

```python
