from __future__ import annotations

from typing import Optional, Protocol, List
from .models import (
    VectorRecord,
    DNFFilter,
    UpsertResult,
    QueryResult,
    FetchResult,
    DeleteResult,
    StatsResult,
)


class VectorStorePort(Protocol):
    def upsert(self, namespace: str, records: List[VectorRecord]) -> UpsertResult: ...

    def query(
        self,
        namespace: str,
        vector: list[float],
        top_k: int,
        flt: Optional[DNFFilter] = None,
    ) -> QueryResult: ...

    def fetch(self, namespace: str, ids: list[str]) -> FetchResult: ...

    def delete(
        self,
        namespace: str,
        ids: Optional[list[str]] = None,
        flt: Optional[DNFFilter] = None,
    ) -> DeleteResult: ...

    def stats(self, namespace: Optional[str] = None) -> StatsResult: ...

---


