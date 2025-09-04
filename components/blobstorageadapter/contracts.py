
from __future__ import annotations
from typing import Any, Dict, Iterable, AsyncIterator, Literal, Optional, Sequence, List
from pydantic import BaseModel, Field, constr, conint

# ---------- Unified Wire Format (UWF) ----------

class ErrorPayload(BaseModel):
    type: Literal["VALIDATION", "NOT_FOUND", "CONFLICT", "UPSTREAM", "INTERNAL"]
    code: constr(strip_whitespace=True, min_length=1)
    message: constr(strip_whitespace=True, min_length=1)
    details: Optional[Dict[str, Any]] = None

class MetaPayload(BaseModel):
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    tenant_id: Optional[str] = None
    duration_ms: Optional[int] = None
    adapter: Optional[str] = None

class UWFResponse(BaseModel):
    ok: bool
    result: Optional[Any] = None
    error: Optional[ErrorPayload] = None
    meta: MetaPayload = Field(default_factory=MetaPayload)

# ---------- Common Models ----------

class BlobRef(BaseModel):
    tenant_id: constr(strip_whitespace=True, min_length=1)
    bucket: constr(strip_whitespace=True, min_length=1)
    key: constr(strip_whitespace=True, min_length=1)

class BlobMeta(BaseModel):
    size: Optional[int] = None
    content_type: Optional[str] = None
    etag: Optional[str] = None
    sha256: Optional[str] = None
    custom: Dict[str, Any] = Field(default_factory=dict)

class PutBlobRequest(BaseModel):
    ref: BlobRef
    data: Optional[bytes] = None
    chunks: Optional[Iterable[bytes]] = None
    content_type: Optional[str] = None
    overwrite: bool = False
    compute_sha256: bool = False

class PutBlobResult(BaseModel):
    ref: BlobRef
    meta: BlobMeta

class GetBlobRequest(BaseModel):
    ref: BlobRef
    range_start: Optional[int] = None
    range_end: Optional[int] = None  # inclusive

class GetBlobResult(BaseModel):
    ref: BlobRef
    meta: BlobMeta
    # content is streamed separately via AsyncIterator[bytes]

class HeadBlobResult(BaseModel):
    ref: BlobRef
    meta: BlobMeta

class DeleteBlobRequest(BaseModel):
    ref: BlobRef
    missing_ok: bool = True

class DeleteBlobResult(BaseModel):
    ref: BlobRef
    deleted: bool

class ListBlobsRequest(BaseModel):
    tenant_id: constr(strip_whitespace=True, min_length=1)
    bucket: constr(strip_whitespace=True, min_length=1)
    prefix: str = ""
    limit: conint(ge=1, le=1000) = 100
    cursor: Optional[str] = None  # opaque

class BlobItem(BaseModel):
    key: str
    meta: BlobMeta

class ListBlobsResult(BaseModel):
    tenant_id: str
    bucket: str
    items: List[BlobItem]
    next_cursor: Optional[str] = None

class PresignOp(str):
    UPLOAD = "upload"
    DOWNLOAD = "download"

class PresignRequest(BaseModel):
    ref: BlobRef
    op: Literal["upload", "download"]
    expires_seconds: conint(gt=0, le=7*24*3600) = 3600
    content_type: Optional[str] = None

class PresignResult(BaseModel):
    url: str
    method: Literal["GET", "PUT"]
    headers: Dict[str, str] = Field(default_factory=dict)
    expires_at_epoch_s: int

