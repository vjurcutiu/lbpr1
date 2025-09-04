from __future__ import annotations

import os
from typing import List, Optional

from ..errors import BackendUnavailable, BadRequest, NamespaceNotFound
from ..models import (
    VectorRecord,
    DNFFilter,
    UpsertResult,
    QueryResult,
    QueryMatch,
    FetchResult,
    DeleteResult,
    StatsResult,
)

# NOTE: This is a lightweight stub to keep the port stable while we wire tests.
# Implement when Pinecone client is available in the environment.

class PineconeVectorStore:
    """
    Pinecone adapter (stub).
    Env:
      VECTORSTORE_PROVIDER=pinecone
      PINECONE_API_KEY=...
      PINECONE_ENVIRONMENT=...
      PINECONE_INDEX=...
    """

    def __init__(self) -> None:
        if not os.getenv("PINECONE_API_KEY"):
            raise BackendUnavailable("Pinecone not configured: missing PINECONE_API_KEY")
        # TODO: initialize real client and index handle
        self._ready = False

    def upsert(self, namespace: str, records: List[VectorRecord]) -> UpsertResult:
        raise BackendUnavailable("Pinecone adapter not implemented yet")

    def query(
        self,
        namespace: str,
        vector: List[float],
        top_k: int,
        flt: Optional[DNFFilter] = None,
    ) -> QueryResult:
        raise BackendUnavailable("Pinecone adapter not implemented yet")

    def fetch(self, namespace: str, ids: List[str]) -> FetchResult:
        raise BackendUnavailable("Pinecone adapter not implemented yet")

    def delete(
        self,
        namespace: str,
        ids: Optional[List[str]] = None,
        flt: Optional[DNFFilter] = None,
    ) -> DeleteResult:
        raise BackendUnavailable("Pinecone adapter not implemented yet")

    def stats(self, namespace: Optional[str] = None) -> StatsResult:
        raise BackendUnavailable("Pinecone adapter not implemented yet")

---


