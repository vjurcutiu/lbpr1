from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, constr


class IngestionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUBMITTED_TO_INDEXER = "SUBMITTED_TO_INDEXER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InlineFile(BaseModel):
    filename: constr(min_length=1)
    bytes_b64: constr(min_length=1) = Field(
        ..., description="Base64-encoded file content"
    )
    content_type: constr(min_length=1) = "application/octet-stream"


class FileRef(BaseModel):
    filename: constr(min_length=1)
    blob_uri: constr(min_length=1)
    content_type: constr(min_length=1) = "application/octet-stream"


class CreateIngestionRequest(BaseModel):
    files: Optional[List[InlineFile]] = None
    file_refs: Optional[List[FileRef]] = None
    source_urls: Optional[List[HttpUrl]] = None
    # Optional client correlation id for idempotency in a future iteration
    client_token: Optional[str] = None

    def total_items(self) -> int:
        return sum(
            [
                len(self.files or []),
                len(self.file_refs or []),
                len(self.source_urls or []),
            ]
        )


class IngestionItem(BaseModel):
    kind: constr(min_length=1)  # "inline_file" | "file_ref" | "url"
    filename: Optional[str] = None
    blob_uri: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    metadata_id: Optional[str] = None


class IngestionEvent(BaseModel):
    type: constr(min_length=1)
    message: str
    ts: float
    data: Dict[str, Any] = Field(default_factory=dict)


class IngestionJob(BaseModel):
    id: str
    tenant_id: str
    status: IngestionStatus
    created_at: float
    updated_at: float
    items: List[IngestionItem] = Field(default_factory=list)
    index_job_id: Optional[str] = None
    events: List[IngestionEvent] = Field(default_factory=list)


class CreateIngestionResponse(BaseModel):
    job: IngestionJob


