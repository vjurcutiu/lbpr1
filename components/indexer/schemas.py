from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class DocInput(BaseModel):
    doc_id: Optional[str] = None
    blob_uri: Optional[str] = None
    text: Optional[str] = None
    fingerprint: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        # collapse excessive whitespace
        return " ".join(str(v).split())


class IndexOptions(BaseModel):
    chunk_size: int = 800
    chunk_overlap: int = 120
    reindex: bool = False
    vector_namespace: Optional[str] = "docs"

    @field_validator("chunk_size")
    @classmethod
    def check_chunk_size(cls, v: int) -> int:
        if v < 100 or v > 4000:
            raise ValueError("chunk_size must be between 100 and 4000")
        return v

    @field_validator("chunk_overlap")
    @classmethod
    def check_overlap(cls, v: int) -> int:
        if v < 0 or v > 1000:
            raise ValueError("chunk_overlap must be between 0 and 1000")
        return v


class CreateIndexJobRequest(BaseModel):
    tenant_id: str
    doc: DocInput
    options: IndexOptions = IndexOptions()


class CreateIndexJobResponse(BaseModel):
    job_id: str
    status: str


class JobCounts(BaseModel):
    chunks_total: int = 0
    chunks_indexed: int = 0
    errors: int = 0


class JobEvent(BaseModel):
    ts: datetime
    type: str
    data: Dict[str, Any]


class JobStatus(BaseModel):
    job_id: str
    tenant_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    counts: JobCounts
    errors: List[str] = Field(default_factory=list)


class JobEventsResponse(BaseModel):
    job_id: str
    events: List[JobEvent]


