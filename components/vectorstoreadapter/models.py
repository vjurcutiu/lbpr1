from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, conlist, validator


# -------- Input / Filter Contracts --------

class FilterCondition(BaseModel):
    field: str = Field(min_length=1)
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "exists"]
    value: Optional[Any] = None


class DNFFilter(BaseModel):
    """
    DNF: (AND groups) OR (AND groups)
    groups: List[List[FilterCondition]] where each inner list is an AND group.
    If groups is empty -> no filter.
    """
    groups: List[List[FilterCondition]] = Field(default_factory=list)


class VectorRecord(BaseModel):
    id: str = Field(min_length=1)
    vector: conlist(float, min_items=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None

    @validator("vector")
    def no_nan_inf(cls, v: List[float]) -> List[float]:
        for x in v:
            if x != x or x in (float("inf"), float("-inf")):
                raise ValueError("vector contains NaN or Inf")
        return v


# -------- Result Contracts --------

class UpsertResult(BaseModel):
    upserted_count: int
    namespace: Optional[str] = None


class QueryMatch(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)
    text: Optional[str] = None


class QueryResult(BaseModel):
    namespace: Optional[str] = None
    matches: List[QueryMatch] = Field(default_factory=list)


class FetchResult(BaseModel):
    namespace: Optional[str] = None
    records: Dict[str, VectorRecord] = Field(default_factory=dict)


class DeleteResult(BaseModel):
    namespace: Optional[str] = None
    deleted_count: int


class StatsResult(BaseModel):
    namespaces: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    # Example: { "tenantA__default": {"vector_count": 123} }

---


