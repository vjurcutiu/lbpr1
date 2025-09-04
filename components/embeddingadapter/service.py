from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import Depends, FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, Field

from .contracts import EmbedRequest, EmbedResult, EmbeddingError
from .adapter_fake import FakeEmbeddingAdapter
from .adapter_openai import OpenAIEmbeddingAdapter

logger = logging.getLogger("embeddingadapter.service")

ProviderName = Literal["fake", "openai"]


class EmbedRequestHttp(BaseModel):
    texts: list[str] = Field(..., min_items=1)
    model: str = "text-embedding-3-small"
    dimensions: Optional[int] = Field(None, ge=8, le=8192)
    normalize: bool = True
    user: Optional[str] = None
    truncate: str = "NONE"
    metadata: dict = Field(default_factory=dict)


class EmbedResponseHttp(BaseModel):
    vectors: list[list[float]]
    model: str
    dimensions: int
    usage: dict
    provider: str
    normalized: bool


def get_adapter(provider: Optional[ProviderName] = None):
    p = provider or os.getenv("EMBEDDING_PROVIDER", "fake")
    model = os.getenv("EMBEDDING_DEFAULT_MODEL", "text-embedding-3-small")
    if p == "fake":
        return FakeEmbeddingAdapter(default_model=model)
    elif p == "openai":
        return OpenAIEmbeddingAdapter(default_model=model)
    else:  # pragma: no cover
        raise RuntimeError(f"Unknown EMBEDDING_PROVIDER={p}")


def router(provider: Optional[ProviderName] = None) -> APIRouter:
    r = APIRouter(prefix="/v1", tags=["embeddings"])
    adapter = get_adapter(provider)

    @r.post("/embeddings", response_model=EmbedResponseHttp)
    def create_embeddings(req: EmbedRequestHttp):
        try:
            result: EmbedResult = adapter.embed(EmbedRequest(**req.dict()))
            return EmbedResponseHttp(**result.dict())
        except EmbeddingError as e:
            logger.warning("Embedding error: %s %s", e.code, e)
            raise HTTPException(status_code=400, detail={"code": e.code, "message": str(e)})
        except Exception as e:  # pragma: no cover
            logger.exception("Unhandled error")
            raise HTTPException(status_code=500, detail={"code": "INTERNAL_ERROR", "message": str(e)})

    return r


def make_app(provider: Optional[ProviderName] = None) -> FastAPI:
    app = FastAPI(title="EmbeddingAdapter", version="0.1")
    app.include_router(router(provider))
    return app


