from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple
from pydantic import BaseModel, Field, conint, constr

# ---------- Unified Wire Format (UWF) ----------

class ErrorPayload(BaseModel):
    type: Literal["AUTH_ERROR","RATE_LIMIT","VALIDATION","NOT_FOUND","CONFLICT","UPSTREAM","INTERNAL"]
    code: constr(strip_whitespace=True, min_length=1)
    message: constr(strip_whitespace=True, min_length=1)
    details: Optional[Dict[str, Any]] = None

class MetaPayload(BaseModel):
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    tenant_id: Optional[str] = None
    duration_ms: Optional[int] = None

class UWFResponse(BaseModel):
    ok: bool
    result: Optional[Any] = None
    error: Optional[ErrorPayload] = None
    meta: MetaPayload

# ---------- Common Models ----------

class AuthContext(BaseModel):
    tenant_id: str
    user_id: str
    scopes: List[str] = Field(default_factory=list)

class FilterCondition(BaseModel):
    field: str
    op: Literal["eq","neq","lt","lte","gt","gte","contains","in","not_in","exists"]
    value: Any

class Filter(BaseModel):
    # DNF support (must=AND, should=OR, must_not=NOT)
    must: List[FilterCondition] = Field(default_factory=list)
    should: List[FilterCondition] = Field(default_factory=list)
    must_not: List[FilterCondition] = Field(default_factory=list)

# ---------- Requests ----------

class CreateIngestionRequest(BaseModel):
    source_hint: Optional[str] = None
    client_job_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

class AppendFilesRequest(BaseModel):
    # either presigned upload tokens OR external URIs
    upload_tokens: List[str] = Field(default_factory=list)
    uris: List[str] = Field(default_factory=list)

class FinalizeIngestionRequest(BaseModel):
    dedupe: bool = True
    reindex: bool = False

class SearchRequest(BaseModel):
    query: str
    top_k: conint(ge=1, le=200) = 20
    filters: Optional[Filter] = None
    rerank: Optional[Literal["none","rrf","zscore"]] = "none"

class ChatMessage(BaseModel):
    role: Literal["system","user","assistant","tool"]
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False
    temperature: float = 0.2
    max_tokens: Optional[int] = None

class SetTagsRequest(BaseModel):
    tags: List[str]

# ---------- Responses (Results) ----------

class HealthResult(BaseModel):
    status: Literal["ok"]
    version: str
    time: str

class IngestionJob(BaseModel):
    job_id: str
    status: Literal["pending","running","completed","failed"]
    files_total: int
    files_ingested: int
    created_at: str
    updated_at: str
    tags: List[str] = Field(default_factory=list)

class SearchHit(BaseModel):
    id: str
    score: float
    metadata: Dict[str, Any]

class SearchResult(BaseModel):
    query: str
    hits: List[SearchHit]
    top_k: int

class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None

class ChatResult(BaseModel):
    choices: List[ChatChoice]
    usage: Optional[Dict[str, Any]] = None

class FileMetadata(BaseModel):
    file_id: str
    size_bytes: int
    mime_type: str
    tags: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
