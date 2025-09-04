from __future__ import annotations

import enum
import hashlib
import logging
import math
import time
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Literal

from pydantic import BaseModel, Field, validator

logger = logging.getLogger("embeddingadapter.contracts")


class EmbeddingError(Exception):
    """Typed error for embedding adapters."""
    def __init__(self, code: str, message: str, *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.code = code
        self.cause = cause


class TruncatePolicy(str, enum.Enum):
    NONE = "NONE"
    START = "START"
    END = "END"


class EmbedRequest(BaseModel):
    texts: List[str] = Field(..., min_items=1, description="Non-empty list of texts to embed")
    model: str = Field("text-embedding-3-small")
    dimensions: Optional[int] = Field(None, ge=8, le=8192)
    normalize: bool = Field(True)
    user: Optional[str] = None
    truncate: TruncatePolicy = TruncatePolicy.NONE
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("texts")
    def _no_empty_texts(cls, v: List[str]) -> List[str]:
        for i, t in enumerate(v):
            if not isinstance(t, str) or not t.strip():
                raise ValueError(f"texts[{i}] is empty")
        return v


class EmbedResult(BaseModel):
    vectors: List[List[float]]
    model: str
    dimensions: int
    usage: Dict[str, int] = Field(default_factory=dict)
    provider: str
    normalized: bool

    @validator("vectors")
    def _vectors_shape(cls, v: List[List[float]]) -> List[List[float]]:
        if not v:
            raise ValueError("vectors must be non-empty")
        dim = len(v[0])
        for i, row in enumerate(v):
            if len(row) != dim:
                raise ValueError(f"row {i} has dim={len(row)} != {dim}")
        return v


@runtime_checkable
class EmbeddingPort(Protocol):
    def embed(self, req: EmbedRequest) -> EmbedResult: ...
    async def aembed(self, req: EmbedRequest) -> EmbedResult: ...


def l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def time_it(func):
    """Simple timing decorator for observability."""
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            dt_ms = round((time.perf_counter() - t0) * 1000, 3)
            logger.info("%s completed in %sms", func.__name__, dt_ms)
    return wrapper


