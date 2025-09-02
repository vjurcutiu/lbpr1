```python
# ./backend/components/apigateway/contracts.py
from __future__ import annotations
# ^ file: ./backend/components/apigateway/contracts.py

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, constr, validator

UWF_VERSION = "1.0"


class Kind(str, Enum):
    command = "command"
    query = "query"


class Actor(BaseModel):
    user_id: constr(min_length=1)
    scopes: List[str] = Field(default_factory=list)


class UWFEnvelope(BaseModel):
    uwf_version: str = Field(default=UWF_VERSION)
    kind: Kind
    trace_id: constr(min_length=1)
    tenant_id: constr(min_length=1)
    actor: Actor
    ts: datetime
    payload: Dict[str, Any]
    meta: Dict[str, Any] = Field(default_factory=dict)

    @validator("uwf_version")
    def _version_fixed(cls, v: str) -> str:
        if v != UWF_VERSION:
            raise ValueError(f"Unsupported UWF version: {v}")
        return v


class ErrorBody(BaseModel):
    code: constr(min_length=3)
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    uwf_version: str = Field(default=UWF_VERSION)
    error: ErrorBody
    trace_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)


# -------- Chat Ask --------
class ChatAskPayload(BaseModel):
    conversation_id: Optional[str] = None
    message: constr(min_length=1)
    stream: bool = False
    context: Dict[str, Any] = Field(default_factory=dict)


class ChatAskResponse(BaseModel):
    conversation_id: str
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)


# -------- Search Query --------
class SearchFusion(str, Enum):
    rrf = "rrf"
    zscore = "zscore"


class SearchQueryPayload(BaseModel):
    query: constr(min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    filters: Dict[str, Any] = Field(default_factory=dict)
    fusion: SearchFusion = SearchFusion.rrf


class SearchQueryResponse(BaseModel):
    results: List[Dict[str, Any]]
    latency_ms: int


# -------- Ingestion --------
class IngestFileDescriptor(BaseModel):
    name: constr(min_length=1)
    size: int = Field(..., ge=0)
    mime: constr(min_length=1)


class IngestInitPayload(BaseModel):
    files: List[IngestFileDescriptor]
    strategy: constr(regex="^(sync|async)$") = "async"


class IngestInitResponse(BaseModel):
    ingestion_id: str
    upload_urls: List[Dict[str, Any]]


class IngestCommitPayload(BaseModel):
    ingestion_id: constr(min_length=1)


class IngestCommitResponse(BaseModel):
    ingestion_id: str
    status: constr(regex="^(queued|processing|done)$")
    files_total: int = Field(..., ge=0)


# -------- Metadata --------
class GetMetadataResponse(BaseModel):
    doc_id: str
    metadata: Dict[str, Any]
    hash: str
python
Copy code
# ./backend/components/apigateway/errors.py
from __future__ import annotations
# ^ file: ./backend/components/apigateway/errors.py

from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel


class ApiGwErrorCode(str, Enum):
    BAD_REQUEST = "APIGW_BAD_REQUEST"
    UNAUTHORIZED = "APIGW_UNAUTHORIZED"
    FORBIDDEN = "APIGW_FORBIDDEN"
    RATE_LIMITED = "APIGW_RATE_LIMITED"
    UPSTREAM_TIMEOUT = "APIGW_UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "APIGW_UPSTREAM_ERROR"
    CONTRACT_VIOLATION = "APIGW_CONTRACT_VIOLATION"
    INTERNAL = "APIGW_INTERNAL"


class PublicError(BaseModel):
    code: ApiGwErrorCode
    message: str
    details: Dict[str, Any] = {}


class UpstreamError(Exception):
    def __init__(self, code: ApiGwErrorCode, message: str, details: Dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
python
Copy code
# ./backend/components/apigateway/ports.py
from __future__ import annotations
# ^ file: ./backend/components/apigateway/ports.py

from typing import Any, Dict, Protocol


class AuthServicePort(Protocol):
    def verify(self, token: str) -> Dict[str, Any]: ...
    def has_scopes(self, claims: Dict[str, Any], required: list[str]) -> bool: ...


class RateLimiterPort(Protocol):
    def check(self, key: str, cost: int = 1) -> bool: ...


class ChatServicePort(Protocol):
    def ask(self, envelope: Dict[str, Any]) -> Dict[str, Any]: ...


class SearchServicePort(Protocol):
    def query(self, envelope: Dict[str, Any]) -> Dict[str, Any]: ...


class IngestionServicePort(Protocol):
    def init_ingestion(self, envelope: Dict[str, Any]) -> Dict[str, Any]: ...
    def commit(self, envelope: Dict[str, Any]) -> Dict[str, Any]: ...


class MetadataServicePort(Protocol):
    def get_metadata(self, tenant_id: str, doc_id: str) -> Dict[str, Any]: ...
python
Copy code
# ./backend/components/apigateway/app.py
from __future__ import annotations
# ^ file: ./backend/components/apigateway/app.py

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .contracts import (
    UWFEnvelope, ErrorEnvelope, ErrorBody,
    ChatAskPayload, ChatAskResponse,
    SearchQueryPayload, SearchQueryResponse,
    IngestInitPayload, IngestInitResponse,
    IngestCommitPayload, IngestCommitResponse,
    GetMetadataResponse, UWF_VERSION
)
from .errors import ApiGwErrorCode, PublicError, UpstreamError
from .ports import (
    AuthServicePort, RateLimiterPort, ChatServicePort, SearchServicePort,
    IngestionServicePort, MetadataServicePort
)

logger = logging.getLogger("apigateway")
logging.basicConfig(level=logging.INFO)

def create_app(
    auth: AuthServicePort,
    rl: RateLimiterPort,
    chat: ChatServicePort,
    search: SearchServicePort,
    ingest: IngestionServicePort,
    meta: MetadataServicePort,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="LBP3 ApiGateway", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Dependencies ---
    async def authn(
        request: Request,
        authorization: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        req_id = x_request_id or str(uuid.uuid4())
        request.state.request_id = req_id

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail=PublicError(
                code=ApiGwErrorCode.UNAUTHORIZED, message="Missing bearer token"
            ).model_dump())

        token = authorization.split(" ", 1)[1]
        try:
            claims = auth.verify(token)
        except Exception as e:  # noqa
            raise HTTPException(status_code=401, detail=PublicError(
                code=ApiGwErrorCode.UNAUTHORIZED, message="Invalid token"
            ).model_dump())

        # Attach base context
        request.state.claims = claims
        request.state.tenant_id = claims.get("tenant_id") or "unknown"
        request.state.actor = {"user_id": claims.get("sub", "unknown"), "scopes": claims.get("scopes", [])}

        dur_ms = int((time.perf_counter() - start) * 1000)
        logger.info(json.dumps({
            "msg": "authn.ok", "trace_id": trace_id, "request_id": req_id, "dur_ms": dur_ms
        }))
        return claims

    async def rate_limit(request: Request) -> None:
        key = f"{getattr(request.state, 'tenant_id', 't?')}:" \
              f"{request.state.actor.get('user_id','u?')}:" \
              f"{request.url.path}"
        if not rl.check(key, cost=1):
            raise HTTPException(status_code=429, detail=PublicError(
                code=ApiGwErrorCode.RATE_LIMITED, message="Rate limit exceeded"
            ).model_dump())

    def build_envelope(request: Request, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "uwf_version": UWF_VERSION,
            "kind": kind,
            "trace_id": request.state.trace_id,
            "tenant_id": request.state.tenant_id,
            "actor": request.state.actor,
            "ts": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
            "meta": {
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            }
        }

    # --- Routes ---
    @app.get("/v1/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/readyz")
    async def readyz():
        return {"status": "ready"}

    @app.get("/v1/version")
    async def version():
        return {"version": app.version}

    @app.post("/v1/chat/ask", response_model=ChatAskResponse)
    async def chat_ask(
        request: Request,
        payload: ChatAskPayload,
        _claims=Depends(authn),
        _rl=Depends(rate_limit),
    ):
        try:
            env = build_envelope(request, "command", payload.model_dump())
            data = chat.ask(env)
            return ChatAskResponse(**data)
        except UpstreamError as ue:
            raise HTTPException(status_code=502, detail=PublicError(code=ue.code, message=str(ue), details=ue.details).model_dump())
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=PublicError(code=ApiGwErrorCode.CONTRACT_VIOLATION, message="Contract violation", details=ve.errors()).model_dump())
        except Exception as e:  # noqa
            logger.exception("chat_ask.unhandled")
            raise HTTPException(status_code=500, detail=PublicError(code=ApiGwErrorCode.INTERNAL, message="Internal error").model_dump())

    @app.post("/v1/search/query", response_model=SearchQueryResponse)
    async def search_query(
        request: Request,
        payload: SearchQueryPayload,
        _claims=Depends(authn),
        _rl=Depends(rate_limit),
    ):
        try:
            env = build_envelope(request, "query", payload.model_dump())
            data = search.query(env)
            return SearchQueryResponse(**data)
        except UpstreamError as ue:
            raise HTTPException(status_code=502, detail=PublicError(code=ue.code, message=str(ue), details=ue.details).model_dump())
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=PublicError(code=ApiGwErrorCode.CONTRACT_VIOLATION, message="Contract violation", details=ve.errors()).model_dump())

    @app.post("/v1/ingest/init", response_model=IngestInitResponse)
    async def ingest_init(
        request: Request,
        payload: IngestInitPayload,
        _claims=Depends(authn),
        _rl=Depends(rate_limit),
    ):
        try:
            env = build_envelope(request, "command", payload.model_dump())
            data = ingest.init_ingestion(env)
            return IngestInitResponse(**data)
        except UpstreamError as ue:
            raise HTTPException(status_code=502, detail=PublicError(code=ue.code, message=str(ue), details=ue.details).model_dump())

    @app.post("/v1/ingest/commit", response_model=IngestCommitResponse)
    async def ingest_commit(
        request: Request,
        payload: IngestCommitPayload,
        _claims=Depends(authn),
        _rl=Depends(rate_limit),
    ):
        try:
            env = build_envelope(request, "command", payload.model_dump())
            data = ingest.commit(env)
            return IngestCommitResponse(**data)
        except UpstreamError as ue:
            raise HTTPException(status_code=502, detail=PublicError(code=ue.code, message=str(ue), details=ue.details).model_dump())

    @app.get("/v1/metadata/{doc_id}", response_model=GetMetadataResponse)
    async def get_metadata(
        request: Request, doc_id: str,
        _claims=Depends(authn),
        _rl=Depends(rate_limit),
    ):
        try:
            data = meta.get_metadata(request.state.tenant_id, doc_id)
            return GetMetadataResponse(**data)
        except UpstreamError as ue:
            raise HTTPException(status_code=502, detail=PublicError(code=ue.code, message=str(ue), details=ue.details).model_dump())

    # Global exception handler to return ErrorEnvelope on HTTPException
    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        body = ErrorEnvelope(
            error=ErrorBody(
                code=exc.detail.get("code", ApiGwErrorCode.INTERNAL) if isinstance(exc.detail, dict) else ApiGwErrorCode.INTERNAL,
                message=exc.detail.get("message", str(exc.detail)) if isinstance(exc.detail, dict) else str(exc.detail),
                details=exc.detail.get("details", {}) if isinstance(exc.detail, dict) else {},
            ),
            trace_id=trace_id,
        )
        return Response(content=body.model_dump_json(), status_code=exc.status_code, media_type="application/json")

    return app
python
Copy code
# ./backend/components/apigateway/main.py
from __future__ import annotations
# ^ file: ./backend/components/apigateway/main.py

import os
from typing import Any, Dict

from .app import create_app

# --- Simple in-memory fakes to keep app runnable for tests/dev ---
class FakeAuth:
    def verify(self, token: str) -> Dict[str, Any]:
        # DO NOT USE IN PROD
        return {"sub": "user_123", "tenant_id": "tenant_abc", "scopes": ["documents:ingest","chat:ask","search:query"]}

    def has_scopes(self, claims: Dict[str, Any], required: list[str]) -> bool:
        return set(required).issubset(set(claims.get("scopes", [])))


class FakeRL:
    def check(self, key: str, cost: int = 1) -> bool:
        return True


class FakeChat:
    def ask(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        msg = envelope["payload"]["message"]
        return {"conversation_id": envelope["payload"].get("conversation_id") or "conv_1", "answer": f"Echo: {msg}", "citations": []}


class FakeSearch:
    def query(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        q = envelope["payload"]["query"]
        return {"results": [{"doc_id":"d1","title":"Doc 1","snippet":f"...{q}...","score":0.9}], "latency_ms": 12}


class FakeIngest:
    def init_ingestion(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        files = envelope["payload"]["files"]
        return {"ingestion_id": "ing_1", "upload_urls": [{"name": f["name"], "url": "https://upload.example"} for f in files]}

    def commit(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        return {"ingestion_id": envelope["payload"]["ingestion_id"], "status": "queued", "files_total": 1}


class FakeMeta:
    def get_metadata(self, tenant_id: str, doc_id: str) -> Dict[str, Any]:
        return {"doc_id": doc_id, "metadata": {"tenant": tenant_id}, "hash": "abc123"}


def build_app():
    cors = (os.environ.get("CORS_ORIGINS") or "").split(",") if os.environ.get("CORS_ORIGINS") else ["*"]
    return create_app(FakeAuth(), FakeRL(), FakeChat(), FakeSearch(), FakeIngest(), FakeMeta(), cors_origins=cors)


app = build_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("APIGW_PORT", "8080")))
python
Copy code
# ./backend/components/apigateway/__init__.py
# marker file for package
python
Copy code
# ./tests/apigateway/test_contracts.py
from __future__ import annotations
# ^ file: ./tests/apigateway/test_contracts.py

from datetime import datetime
from backend.components.apigateway.contracts import (
    UWFEnvelope, Kind, Actor, ChatAskPayload, SearchQueryPayload, IngestInitPayload, IngestCommitPayload
)


def test_envelope_version_lock():
    env = UWFEnvelope(
        kind=Kind.command,
        trace_id="t1",
        tenant_id="tenant",
        actor=Actor(user_id="u1", scopes=["a"]),
        ts=datetime.utcnow(),
        payload={"k":"v"},
        meta={"m":"n"}
    )
    assert env.uwf_version == "1.0"


def test_chat_payload_minimal():
    p = ChatAskPayload(message="Hello")
    assert p.stream is False


def test_search_payload_defaults():
    p = SearchQueryPayload(query="law")
    assert p.top_k == 10
    assert p.fusion.value in ("rrf","zscore")


def test_ingest_init_required():
    p = IngestInitPayload(files=[{"name":"a.pdf","size":1,"mime":"application/pdf"}])
    assert p.strategy in ("sync","async")


def test_ingest_commit_required():
    p = IngestCommitPayload(ingestion_id="ing_1")
    assert p.ingestion_id == "ing_1"
python
Copy code
# ./tests/apigateway/test_routes.py
from __future__ import annotations
# ^ file: ./tests/apigateway/test_routes.py

from fastapi.testclient import TestClient
from backend.components.apigateway.main import build_app

AUTH = {"Authorization": "Bearer fake"}


def client():
    return TestClient(build_app())


def test_health():
    c = client()
    r = c.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_ask():
    c = client()
    r = c.post("/v1/chat/ask", json={"message": "Hello"}, headers=AUTH)
    assert r.status_code == 200
    js = r.json()
    assert js["answer"].startswith("Echo:")


def test_search_query():
    c = client()
    r = c.post("/v1/search/query", json={"query": "contract"}, headers=AUTH)
    assert r.status_code == 200
    assert "results" in r.json()


def test_ingest_flow():
    c = client()
    r1 = c.post("/v1/ingest/init", json={"files":[{"name":"a.pdf","size":10,"mime":"application/pdf"}]}, headers=AUTH)
    assert r1.status_code == 200
    ing_id = r1.json()["ingestion_id"]
    r2 = c.post("/v1/ingest/commit", json={"ingestion_id": ing_id}, headers=AUTH)
    assert r2.status_code == 200
    assert r2.json()["status"] in ("queued","processing","done")
toml
Copy code
# ./backend/components/apigateway/pyproject.toml
[project]
name = "lbp3-apigateway"
version = "0.1.0"
dependencies = [
  "fastapi>=0.111",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
]

[tool.pytest.ini_options]
pythonpath = ["."]