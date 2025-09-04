from __future__ import annotations

import hashlib
import logging
from typing import List

from .contracts import EmbedRequest, EmbedResult, EmbeddingError, l2_normalize, time_it

logger = logging.getLogger("embeddingadapter.fake")


def _hash_to_floats(seed: str, dims: int) -> List[float]:
    """Deterministic pseudo-embedding from text hash → floats in [-1, 1]."""
    # Expand bytes via repeated hashing to reach dims
    buf = bytearray()
    cur = seed.encode("utf-8")
    while len(buf) < dims * 4:
        cur = hashlib.sha256(cur).digest()
        buf.extend(cur)
    # Convert 4-byte chunks to floats in [-1, 1]
    out: List[float] = []
    for i in range(dims):
        chunk = buf[4 * i : 4 * (i + 1)]
        n = int.from_bytes(chunk, "big", signed=False)
        # Map to [-1, 1]
        out.append((n % 2000000) / 1000000.0 - 1.0)
    return out


class FakeEmbeddingAdapter:
    """Deterministic, zero-dependency adapter for tests and local dev."""

    provider_name = "fake"

    def __init__(self, default_model: str = "text-embedding-3-small", default_dims: int = 1536):
        self.default_model = default_model
        self.default_dims = default_dims

    @time_it
    def embed(self, req: EmbedRequest) -> EmbedResult:
        dims = req.dimensions or self.default_dims
        vectors = []
        for t in req.texts:
            v = _hash_to_floats(f"{req.model}:{dims}:{t}", dims)
            if req.normalize:
                v = l2_normalize(v)
            vectors.append(v)

        usage = {"prompt_texts": len(req.texts)}
        logger.info(
            "fake.embed batch=%d dims=%d model=%s normalize=%s",
            len(req.texts), dims, req.model, req.normalize
        )
        return EmbedResult(
            vectors=vectors,
            model=req.model,
            dimensions=dims,
            usage=usage,
            provider=self.provider_name,
            normalized=req.normalize,
        )

    async def aembed(self, req: EmbedRequest) -> EmbedResult:
        # For the fake adapter the async path just delegates
        return self.embed(req)


