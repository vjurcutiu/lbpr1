from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi import FastAPI
from pydantic import BaseModel

from .contracts import (
    EmbeddingAdapterPort,
    SearchRequest,
)
from .core import execute_search
from .adapters_inmemory import (
    InMemoryEmbeddingAdapter,
    InMemoryVectorStoreAdapter,
)

logger = logging.getLogger("searchservice")
router = APIRouter(prefix="/search", tags=["search"])


# --- Dependency Injection (simple) ---
class Container(BaseModel):
    embedding: EmbeddingAdapterPort
    vector: InMemoryVectorStoreAdapter  # still conforms to VectorStoreAdapterPort


_container = Container(
    embedding=InMemoryEmbeddingAdapter(),
    vector=InMemoryVectorStoreAdapter.bootstrap_sample(),
)


def get_container() -> Container:
    return _container


# --- Auth (placeholder) ---
def get_tenant_id(x_debug_bypass_auth: Optional[str] = Header(None)) -> str:
    # v0.1: allow tests to bypass; production should validate JWT and extract tenant claim
    if x_debug_bypass_auth == "1":
        return "test-tenant"
    # If not bypassed, fail auth (until wired to AuthService)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Auth required. Provide X-Debug-Bypass-Auth: 1 for tests in v0.1.",
    )


@router.get("/health")
async def health(container: Container = Depends(get_container)):
    try:
        # quick probe by calling vector adapter count
        total = container.vector.count_documents()
        return {"status": "ok", "docs": total}
    except Exception as e:
        logger.exception("health check failed: %s", e)
        raise HTTPException(status_code=500, detail="unhealthy")


@router.post("", response_model=None)
async def post_search(
    payload: SearchRequest,
    tenant_id: str = Depends(get_tenant_id),
    container: Container = Depends(get_container),
):
    request_id = str(uuid.uuid4())
    logger.info(
        "search.request start request_id=%s tenant=%s top_k=%s type=%s",
        request_id, tenant_id, payload.top_k, payload.search_type,
    )
    try:
        resp = await execute_search(
            tenant_id=tenant_id,
            req=payload,
            embedding=container.embedding,
            vector_store=container.vector,
        )
        # include request_id in logs; client already receives query_id; we keep request_id internal
        logger.info(
            "search.request end request_id=%s tenant=%s took_ms=%s total=%s",
            request_id, tenant_id, resp.took_ms, resp.total
        )
        return resp.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("search failed request_id=%s: %s", request_id, e)
        raise HTTPException(status_code=500, detail="search failed")


def create_app() -> FastAPI:
    app = FastAPI(title="SearchService")
    app.include_router(router)
    return app

---

```python
