from __future__ import annotations

import logging
import os
from typing import Optional

from .contracts import EmbedRequest, EmbedResult, EmbeddingError, l2_normalize, time_it

logger = logging.getLogger("embeddingadapter.openai")

# Note: We keep this optional to avoid test deps.
try:
    # The modern OpenAI SDK (>=1.0) has a client like this:
    from openai import OpenAI  # type: ignore
    _HAS_OPENAI = True
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore
    _HAS_OPENAI = False


class OpenAIEmbeddingAdapter:
    provider_name = "openai"

    def __init__(self, default_model: str = "text-embedding-3-small"):
        self.default_model = default_model
        self._client = None
        if _HAS_OPENAI:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set; adapter will raise on use.")
            else:
                self._client = OpenAI(api_key=api_key)  # type: ignore

    @time_it
    def embed(self, req: EmbedRequest) -> EmbedResult:
        if not _HAS_OPENAI or self._client is None:
            raise EmbeddingError("CONFIG_ERROR", "OpenAI SDK not available or API key not set.")

        model = req.model or self.default_model
        try:
            kwargs = dict(model=model, input=req.texts)
            if req.dimensions is not None:
                kwargs["dimensions"] = req.dimensions
            if req.user:
                kwargs["user"] = req.user

            resp = self._client.embeddings.create(**kwargs)  # type: ignore
            # SDK typically returns .data[i].embedding and .usage
            vectors = [d.embedding for d in resp.data]  # type: ignore[attr-defined]
            dims = len(vectors[0]) if vectors else (req.dimensions or 0)
            if req.normalize:
                vectors = [l2_normalize(v) for v in vectors]

            usage = {}
            if getattr(resp, "usage", None) is not None:
                # Some SDKs: usage.prompt_tokens / total_tokens
                usage = {
                    k: int(v) for k, v in resp.usage.__dict__.items() if isinstance(v, int)  # type: ignore
                }
            logger.info(
                "openai.embed batch=%d dims=%s model=%s normalize=%s",
                len(req.texts), dims, model, req.normalize
            )
            return EmbedResult(
                vectors=vectors,
                model=model,
                dimensions=dims,
                usage=usage,
                provider=self.provider_name,
                normalized=req.normalize,
            )
        except EmbeddingError:
            raise
        except Exception as e:  # pragma: no cover
            logger.exception("OpenAI provider error")
            raise EmbeddingError("PROVIDER_ERROR", str(e), cause=e)

    async def aembed(self, req: EmbedRequest) -> EmbedResult:
        # Simple sync delegate to keep complexity low for now.
        return self.embed(req)


