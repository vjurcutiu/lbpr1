66696c657374617274 ./components/apigateway/contracts.py
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
python
Copy code
66696c657374617274 ./components/apigateway/errors.py
from __future__ import annotations
from typing import Dict, Optional
from pydantic import BaseModel

class ApiGatewayError(Exception):
    type: str = "INTERNAL"
    code: str = "internal_error"
    message: str = "Internal server error"
    details: Optional[Dict] = None
    status_code: int = 500

    def to_payload(self):
        return {
            "type": self.type,
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }

class AuthError(ApiGatewayError):
    type = "AUTH_ERROR"
    code = "auth_failed"
    message = "Authentication failed"
    status_code = 401

class ForbiddenError(ApiGatewayError):
    type = "AUTH_ERROR"
    code = "forbidden"
    message = "Not enough privileges"
    status_code = 403

class RateLimitError(ApiGatewayError):
    type = "RATE_LIMIT"
    code = "rate_limited"
    message = "Rate limit exceeded"
    status_code = 429

class ValidationError(ApiGatewayError):
    type = "VALIDATION"
    code = "validation_error"
    message = "Validation error"
    status_code = 422

class NotFoundError(ApiGatewayError):
    type = "NOT_FOUND"
    code = "not_found"
    message = "Resource not found"
    status_code = 404

class UpstreamError(ApiGatewayError):
    type = "UPSTREAM"
    code = "upstream_error"
    message = "Upstream dependency failed"
    status_code = 502
python
Copy code
66696c657374617274 ./components/apigateway/ports.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Protocol
from .contracts import (
    AuthContext, CreateIngestionRequest, AppendFilesRequest,
    FinalizeIngestionRequest, IngestionJob, SearchRequest, SearchResult,
    ChatCompletionRequest, ChatResult, FileMetadata
)

# These are the *interfaces* (ports). Adapters will implement these.

class AuthPort(Protocol):
    def verify_token(self, token: str) -> AuthContext: ...
    def authorize(self, ctx: AuthContext, scopes: List[str]) -> None: ...

class RateLimiterPort(Protocol):
    def check(self, key: str, cost: int = 1) -> None: ...
    def consume(self, key: str, cost: int = 1) -> None: ...

class IngestionPort(Protocol):
    def create_job(self, ctx: AuthContext, req: CreateIngestionRequest) -> IngestionJob: ...
    def append_files(self, ctx: AuthContext, job_id: str, req: AppendFilesRequest) -> IngestionJob: ...
    def finalize_job(self, ctx: AuthContext, job_id: str, req: FinalizeIngestionRequest) -> IngestionJob: ...
    def get_job(self, ctx: AuthContext, job_id: str) -> IngestionJob: ...

class SearchPort(Protocol):
    def search(self, ctx: AuthContext, req: SearchRequest) -> SearchResult: ...

class ChatPort(Protocol):
    def completion(self, ctx: AuthContext, req: ChatCompletionRequest) -> ChatResult: ...

class MetadataPort(Protocol):
    def get_file_metadata(self, ctx: AuthContext, file_id: str) -> FileMetadata: ...
    def set_tags(self, ctx: AuthContext, file_id: str, tags: List[str]) -> FileMetadata: ...
python
Copy code
66696c657374617274 ./components/apigateway/settings.py
from __future__ import annotations
import os

APP_NAME = "lbp3-rs-apigateway"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
REQUEST_BODY_MAX_BYTES = int(os.getenv("APIGW_BODY_MAX_BYTES", "10485760"))  # 10 MiB

# Rate limits (example defaults)
LIMIT_SEARCH_PER_MIN = int(os.getenv("APIGW_LIMIT_SEARCH_PER_MIN", "120"))
LIMIT_CHAT_PER_MIN = int(os.getenv("APIGW_LIMIT_CHAT_PER_MIN", "60"))
LIMIT_INGEST_PER_MIN = int(os.getenv("APIGW_LIMIT_INGEST_PER_MIN", "30"))
python
Copy code
66696c657374617274 ./components/apigateway/observability.py
from __future__ import annotations
import time, uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger("apigateway")

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        tenant_id = request.headers.get("x-tenant-id")  # optional mirror
        # In real use, we would fetch/attach trace_id from OTel context
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())

        request.state.request_id = request_id
        request.state.tenant_id = tenant_id
        request.state.trace_id = trace_id

        logger.info(
            "request.start",
            extra={"request_id": request_id, "trace_id": trace_id, "path": request.url.path, "method": request.method}
        )
        try:
            response: Response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers["x-request-id"] = request_id
            response.headers["x-trace-id"] = trace_id
            logger.info(
                "request.end",
                extra={"request_id": request_id, "trace_id": trace_id, "status": response.status_code, "duration_ms": duration_ms}
            )
            return response
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "request.exception",
                extra={"request_id": request_id, "trace_id": trace_id, "duration_ms": duration_ms}
            )
            raise
python
Copy code
66696c657374617274 ./components/apigateway/app.py
from __future__ import annotations
from fastapi import FastAPI
from .observability import RequestContextMiddleware
from .settings import APP_NAME, APP_VERSION
from .routers import public

def create_app() -> FastAPI:
    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    app.add_middleware(RequestContextMiddleware)

    # Routers
    app.include_router(public.router, prefix="/v1")

    return app

app = create_app()
python
Copy code
66696c657374617274 ./components/apigateway/routers/public.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from ..contracts import (
    UWFResponse, MetaPayload, ErrorPayload, HealthResult,
    CreateIngestionRequest, AppendFilesRequest, FinalizeIngestionRequest,
    IngestionJob, SearchRequest, SearchResult, ChatCompletionRequest, ChatResult,
    FileMetadata, SetTagsRequest, AuthContext
)
from ..errors import (
    AuthError, ForbiddenError, RateLimitError, ValidationError as VErr,
    NotFoundError, UpstreamError, ApiGatewayError
)
from ..settings import APP_VERSION
from ..ports import AuthPort, RateLimiterPort, IngestionPort, SearchPort, ChatPort, MetadataPort

router = APIRouter()

# ---- Dependency placeholders (to be wired by DI container or test doubles) ----
# In production, these will be provided by adapters; for now we use simple fakes.

class _FakeAuth(AuthPort):
    def verify_token(self, token: str) -> AuthContext:
        if not token or token == "invalid":
            raise AuthError()
        # trivial demo parse
        return AuthContext(tenant_id="t_demo", user_id="u_demo", scopes=["documents:ingest","search:query","chat:send"])

    def authorize(self, ctx: AuthContext, scopes: List[str]) -> None:
        missing = [s for s in scopes if s not in ctx.scopes]
        if missing:
            raise ForbiddenError()

class _NoopRL(RateLimiterPort):
    def check(self, key: str, cost: int = 1) -> None: return None
    def consume(self, key: str, cost: int = 1) -> None: return None

class _FakeIngest(IngestionPort):
    def __init__(self): self._jobs: Dict[str, IngestionJob] = {}
    def create_job(self, ctx: AuthContext, req: CreateIngestionRequest) -> IngestionJob:
        job = IngestionJob(job_id="job_1", status="pending", files_total=0, files_ingested=0,
                           created_at="now", updated_at="now", tags=req.tags or [])
        self._jobs[job.job_id] = job
        return job
    def append_files(self, ctx: AuthContext, job_id: str, req: AppendFilesRequest) -> IngestionJob:
        job = self._jobs.get(job_id)
        if not job: raise NotFoundError()
        added = len(req.upload_tokens) + len(req.uris)
        job.files_total += added
        job.updated_at = "now"
        return job
    def finalize_job(self, ctx: AuthContext, job_id: str, req: FinalizeIngestionRequest) -> IngestionJob:
        job = self._jobs.get(job_id)
        if not job: raise NotFoundError()
        job.status = "completed"
        job.files_ingested = job.files_total
        job.updated_at = "now"
        return job
    def get_job(self, ctx: AuthContext, job_id: str) -> IngestionJob:
        job = self._jobs.get(job_id)
        if not job: raise NotFoundError()
        return job

class _FakeSearch(SearchPort):
    def search(self, ctx: AuthContext, req: SearchRequest) -> SearchResult:
        return SearchResult(query=req.query, hits=[], top_k=req.top_k)

class _FakeChat(ChatPort):
    def completion(self, ctx: AuthContext, req: ChatCompletionRequest) -> ChatResult:
        choice = {"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
        return ChatResult(choices=[choice], usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})

class _FakeMeta(MetadataPort):
    def get_file_metadata(self, ctx: AuthContext, file_id: str) -> FileMetadata:
        return FileMetadata(file_id=file_id, size_bytes=123, mime_type="text/plain", tags=["demo"], created_at="now", updated_at="now")
    def set_tags(self, ctx: AuthContext, file_id: str, tags: List[str]) -> FileMetadata:
        return FileMetadata(file_id=file_id, size_bytes=123, mime_type="text/plain", tags=tags, created_at="now", updated_at="now")

_auth: AuthPort = _FakeAuth()
_rl: RateLimiterPort = _NoopRL()
_ing: IngestionPort = _FakeIngest()
_search: SearchPort = _FakeSearch()
_chat: ChatPort = _FakeChat()
_meta: MetadataPort = _FakeMeta()

# ---- Helpers ----

def _uwf_ok(request: Request, result: Any) -> UWFResponse:
    meta = MetaPayload(
        trace_id=getattr(request.state, "trace_id", None),
        request_id=getattr(request.state, "request_id", None),
        tenant_id=getattr(request.state, "tenant_id", None),
    )
    return UWFResponse(ok=True, result=result, error=None, meta=meta)

def _uwf_err(request: Request, err: ApiGatewayError):
    meta = MetaPayload(
        trace_id=getattr(request.state, "trace_id", None),
        request_id=getattr(request.state, "request_id", None),
        tenant_id=getattr(request.state, "tenant_id", None),
    )
    return UWFResponse(ok=False, result=None, error=ErrorPayload(**err.to_payload()), meta=meta)

def _auth_ctx(authorization: Optional[str]) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError()
    token = authorization.split(" ", 1)[1].strip()
    return _auth.verify_token(token)

# ---- Routes ----

@router.get("/health", response_model=UWFResponse)
def health(request: Request):
    return _uwf_ok(request, HealthResult(status="ok", version=APP_VERSION, time="now"))

@router.get("/ready", response_model=UWFResponse)
def ready(request: Request):
    return _uwf_ok(request, {"ready": True})

@router.post("/ingestions", response_model=UWFResponse)
def create_ingestion(request: Request, body: CreateIngestionRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        _rl.check(f"ingest:{ctx.tenant_id}")
        job = _ing.create_job(ctx, body)
        _rl.consume(f"ingest:{ctx.tenant_id}")
        return _uwf_ok(request, job)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.post("/ingestions/{job_id}/files", response_model=UWFResponse)
def append_files(job_id: str, request: Request, body: AppendFilesRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        job = _ing.append_files(ctx, job_id, body)
        return _uwf_ok(request, job)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.post("/ingestions/{job_id}/finalize", response_model=UWFResponse)
def finalize(job_id: str, request: Request, body: FinalizeIngestionRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        job = _ing.finalize_job(ctx, job_id, body)
        return _uwf_ok(request, job)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.get("/ingestions/{job_id}", response_model=UWFResponse)
def get_ingestion(job_id: str, request: Request, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        job = _ing.get_job(ctx, job_id)
        return _uwf_ok(request, job)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.post("/search", response_model=UWFResponse)
def search(request: Request, body: SearchRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["search:query"])
        _rl.check(f"search:{ctx.tenant_id}")
        res = _search.search(ctx, body)
        _rl.consume(f"search:{ctx.tenant_id}")
        return _uwf_ok(request, res)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.post("/chat/completions", response_model=UWFResponse)
def chat_completions(request: Request, body: ChatCompletionRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["chat:send"])
        _rl.check(f"chat:{ctx.tenant_id}")
        res = _chat.completion(ctx, body)
        _rl.consume(f"chat:{ctx.tenant_id}")
        return _uwf_ok(request, res)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.get("/files/{file_id}/metadata", response_model=UWFResponse)
def get_metadata(file_id: str, request: Request, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        res = _meta.get_file_metadata(ctx, file_id)
        return _uwf_ok(request, res)
    except ApiGatewayError as e:
        return _uwf_err(request, e)

@router.post("/files/{file_id}/tags", response_model=UWFResponse)
def set_tags(file_id: str, request: Request, body: SetTagsRequest, authorization: Optional[str] = Header(default=None)):
    try:
        ctx = _auth_ctx(authorization)
        _auth.authorize(ctx, ["documents:ingest"])
        res = _meta.set_tags(ctx, file_id, body.tags)
        return _uwf_ok(request, res)
    except ApiGatewayError as e:
        return _uwf_err(request, e)
python
Copy code
66696c657374617274 ./tests/test_apigateway_contracts.py
import pytest
from components.apigateway.contracts import (
    UWFResponse, ErrorPayload, MetaPayload, SearchRequest, ChatCompletionRequest, ChatMessage
)

def test_uwf_success_shape():
    resp = UWFResponse(ok=True, result={"x": 1}, error=None, meta=MetaPayload(trace_id="t", request_id="r"))
    assert resp.ok is True
    assert resp.result == {"x": 1}
    assert resp.error is None
    assert resp.meta.trace_id == "t"

def test_uwf_error_shape():
    err = ErrorPayload(type="VALIDATION", code="bad_input", message="nope")
    resp = UWFResponse(ok=False, result=None, error=err, meta=MetaPayload())
    assert resp.ok is False
    assert resp.result is None
    assert resp.error.code == "bad_input"

def test_search_request_validation():
    s = SearchRequest(query="hello", top_k=10)
    assert s.top_k == 10
    with pytest.raises(Exception):
        SearchRequest(query="hello", top_k=0)

def test_chat_completion_request():
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.messages[0].role == "user"
python
Copy code
66696c657374617274 ./tests/test_apigateway_routes.py
from fastapi.testclient import TestClient
from components.apigateway.app import create_app

def _client():
    app = create_app()
    return TestClient(app)

AUTH = {"Authorization": "Bearer demo"}

def test_health():
    c = _client()
    r = c.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["status"] == "ok"

def test_create_ingestion_requires_auth():
    c = _client()
    r = c.post("/v1/ingestions", json={"tags": ["x"]})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["type"] == "AUTH_ERROR"

def test_create_ingestion_success():
    c = _client()
    r = c.post("/v1/ingestions", headers=AUTH, json={"tags": ["alpha"]})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["status"] == "pending"
    job_id = body["result"]["job_id"]

    r2 = c.post(f"/v1/ingestions/{job_id}/files", headers=AUTH, json={"uris": ["s3://demo/a.txt"]})
    assert r2.json()["ok"] is True
    assert r2.json()["result"]["files_total"] == 1

    r3 = c.post(f"/v1/ingestions/{job_id}/finalize", headers=AUTH, json={"dedupe": True})
    assert r3.json()["ok"] is True
    assert r3.json()["result"]["status"] == "completed"

def test_search_and_chat():
    c = _client()
    s = c.post("/v1/search", headers=AUTH, json={"query": "hello", "top_k": 5})
    assert s.json()["ok"] is True
    ch = c.post("/v1/chat/completions", headers=AUTH, json={"messages": [{"role":"user","content":"hi"}]})
    assert ch.json()["ok"] is True
    assert ch.json()["result"]["choices"][0]["message"]["content"] == "Hello!"
python
Copy code
66696c657374617274 ./components/apigateway/__init__.py
# Package marker for apigateway