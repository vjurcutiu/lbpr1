from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, conint, validator


# ---------- Errors ----------
class SearchError(Exception):
    """Generic search failure."""


class AdapterError(SearchError):
    """Raised when an adapter/port fails."""


class UnauthorizedError(SearchError):
    """Auth required or invalid."""


class ValidationError(SearchError):
    """Bad request contents."""


# ---------- Enums ----------
class SearchType(str, enum.Enum):
    semantic = "semantic"
    keyword = "keyword"
    hybrid = "hybrid"


class Fusion(str, enum.Enum):
    rrf = "rrf"
    zscore = "zscore"


# ---------- Filters (DNF) ----------
class Op(str, enum.Enum):
    eq = "eq"
    ne = "ne"
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    contains = "contains"
    in_ = "in"        # list membership
    nin = "nin"       # not in


class FilterCondition(BaseModel):
    field: str
    op: Op
    value: Any


class Filter(BaseModel):
    # DNF: (AND groups) OR (AND groups) — simplified here as top-level must/should/must_not
    must: List[FilterCondition] = Field(default_factory=list)
    should: List[FilterCondition] = Field(default_factory=list)
    must_not: List[FilterCondition] = Field(default_factory=list)


# ---------- Requests / Responses ----------
class SearchRequest(BaseModel):
    query: Optional[str] = Field(None, description="Query text (optional if pure filter search).")
    top_k: conint(ge=1, le=200) = 10
    offset: conint(ge=0, le=10000) = 0
    search_type: SearchType = SearchType.semantic
    fusion: Optional[Fusion] = None
    filters: Filter = Field(default_factory=Filter)
    include_snippets: bool = True
    snippet_max_chars: conint(ge=32, le=1000) = 240
    metadata_fields: List[str] = Field(default_factory=list)

    @validator("fusion")
    def validate_fusion(cls, v, values):
        if v is not None and values.get("search_type") != SearchType.hybrid:
            raise ValueError("fusion can only be set when search_type='hybrid'")
        return v


class SearchHit(BaseModel):
    doc_id: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query_id: str
    took_ms: int
    total: int
    hits: List[SearchHit]


# ---------- Ports (Adapters) ----------
class EmbeddingAdapterPort:
    """Port for computing query embeddings."""

    async def embed_query(self, text: str) -> List[float]:
        raise NotImplementedError


@dataclass
class VectorHit:
    doc_id: str
    score: float
    metadata: Dict[str, Any]
    snippet: Optional[str]


class VectorHits(BaseModel):
    total: int
    hits: List[VectorHit]  # pydantic will accept dataclasses as well


class VectorStoreAdapterPort:
    """Port for vector similarity search."""

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
        raise NotImplementedError
