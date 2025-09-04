from __future__ import annotations

import math
import time
from typing import Dict, List, Optional

from ..errors import BadRequest, NamespaceNotFound
from ..models import (
    VectorRecord,
    DNFFilter,
    FilterCondition,
    UpsertResult,
    QueryResult,
    QueryMatch,
    FetchResult,
    DeleteResult,
    StatsResult,
)


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise BadRequest("query vector dimensionality mismatch")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _eval_condition(md: dict, c: FilterCondition) -> bool:
    exists = c.field in md
    val = md.get(c.field)
    if c.op == "exists":
        return exists
    if c.op == "eq":
        return val == c.value
    if c.op == "neq":
        return val != c.value
    if c.op == "gt":
        return exists and val > c.value
    if c.op == "gte":
        return exists and val >= c.value
    if c.op == "lt":
        return exists and val < c.value
    if c.op == "lte":
        return exists and val <= c.value
    if c.op == "in":
        return exists and val in (c.value or [])
    if c.op == "nin":
        return not exists or val not in (c.value or [])
    return False


def _match_filter(md: dict, flt: Optional[DNFFilter]) -> bool:
    if not flt or not flt.groups:
        return True
    # DNF: any AND group satisfied -> pass
    for and_group in flt.groups:
        if all(_eval_condition(md, c) for c in and_group):
            return True
    return False


class InMemoryVectorStore:
    """
    Simple, deterministic, test-friendly adapter.
    Storage: { namespace: { id: VectorRecord } }
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, VectorRecord]] = {}

    # -------- Port methods --------

    def upsert(self, namespace: str, records: List[VectorRecord]) -> UpsertResult:
        t0 = time.perf_counter()
        if not namespace:
            raise BadRequest("namespace required")
        ns = self._store.setdefault(namespace, {})
        for r in records:
            # Pydantic already validated r
            ns[r.id] = r
        dt = (time.perf_counter() - t0) * 1000
        # Simple observability
        # (Replace with your logger)
        # print(f"[InMemoryVectorStore] upsert ns={namespace} n={len(records)} ms={dt:.2f}")
        return UpsertResult(upserted_count=len(records), namespace=namespace)

    def query(
        self,
        namespace: str,
        vector: List[float],
        top_k: int,
        flt: Optional[DNFFilter] = None,
    ) -> QueryResult:
        t0 = time.perf_counter()
        ns = self._store.get(namespace)
        if ns is None:
            raise NamespaceNotFound(f"namespace={namespace}")
        scored: List[QueryMatch] = []
        for rec in ns.values():
            if not _match_filter(rec.metadata, flt):
                continue
            score = _cosine(vector, rec.vector)
            scored.append(
                QueryMatch(
                    id=rec.id,
                    score=score,
                    metadata=rec.metadata,
                    text=rec.text,
                )
            )
        scored.sort(key=lambda m: m.score, reverse=True)
        out = QueryResult(namespace=namespace, matches=scored[: max(0, top_k)])
        dt = (time.perf_counter() - t0) * 1000
        # print(f"[InMemoryVectorStore] query ns={namespace} top_k={top_k} ms={dt:.2f}")
        return out

    def fetch(self, namespace: str, ids: List[str]) -> FetchResult:
        ns = self._store.get(namespace)
        if ns is None:
            raise NamespaceNotFound(f"namespace={namespace}")
        found = {i: ns[i] for i in ids if i in ns}
        return FetchResult(namespace=namespace, records=found)

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        flt: Optional[DNFFilter] = None,
    ) -> DeleteResult:
        ns = self._store.get(namespace)
        if ns is None:
            raise NamespaceNotFound(f"namespace={namespace}")
        deleted = 0
        if ids:
            for i in ids:
                if i in ns:
                    del ns[i]
                    deleted += 1
        elif flt:
            to_del = [rid for rid, rec in ns.items() if _match_filter(rec.metadata, flt)]
            for rid in to_del:
                del ns[rid]
                deleted += 1
        else:
            # delete whole namespace contents
            deleted = len(ns)
            ns.clear()
        return DeleteResult(namespace=namespace, deleted_count=deleted)

    def stats(self, namespace: Optional[str] = None) -> StatsResult:
        if namespace:
            ns = self._store.get(namespace)
            count = 0 if ns is None else len(ns)
            return StatsResult(namespaces={namespace: {"vector_count": count}})
        return StatsResult(
            namespaces={ns: {"vector_count": len(recs)} for ns, recs in self._store.items()}
        )

---


