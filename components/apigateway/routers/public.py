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
