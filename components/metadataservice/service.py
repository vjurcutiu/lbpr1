"""
MetadataService Implementation (v0.1) — FastAPI router + in-memory adapters

Project: lbp3-rs
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi import Response
from pydantic import BaseModel

from .contracts import (
    BlobNotFoundError,
    BlobReaderPort,
    Envelope,
    ExtractBlobInput,
    ExtractRequest,
    ExtractResponse,
    ExtractTextInput,
    InvalidInputError,
    KeywordExtractorPort,
    LLMAdapterPort,
    LLMFailedError,
    MetadataRecord,
    MetadataStorePort,
    Stats,
    StoreFailedError,
)

# Observability: logger + optional OpenTelemetry spans (no hard dependency)
logger = logging.getLogger("lbp3.metadataservice")
logger.setLevel(logging.INFO)


def _try_span(name: str):
    """Context manager that starts a noop span if otel not available."""
    class _Noop:
        def __enter__(self): return None
        def __exit__(self, exc_type, exc, tb): return False
    try:
        from opentelemetry import trace  # type: ignore
        tracer = trace.get_tracer("lbp3.metadataservice")
        return tracer.start_as_current_span(name)
    except Exception:
        return _Noop()


# --------------------------
# Defaults: In-memory adapters (test-friendly)
# --------------------------

class InMemoryBlobReader(BlobReaderPort):
    def __init__(self, blobs: Optional[Dict[str, bytes]] = None):
        self._blobs = blobs or {}

    def read(self, blob_uri: str) -> bytes:
        if blob_uri not in self._blobs:
            raise BlobNotFoundError(f"Blob not found: {blob_uri}")
        return self._blobs[blob_uri]


class SimpleKeywordExtractor(KeywordExtractorPort):
    _STOPWORDS = {
        "en": {
            "the","a","an","and","or","but","if","then","else","for","of","to","in","on","at","by","with",
            "is","are","was","were","be","been","it","that","this","these","those","as","from","we","you",
        }
    }

    def top_keywords(self, text: str, top_k: int = 10, language_hint: Optional[str] = None) -> List[str]:
        lang = language_hint or "en"
        stop = self._STOPWORDS.get(lang, set())
        tokens = re.findall(r"[A-Za-z0-9']{2,}", text.lower())
        freq: Dict[str, int] = {}
        for t in tokens:
            if t in stop or t.isdigit():
                continue
            freq[t] = freq.get(t, 0) + 1
        sorted_tokens = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
        return [w for w, _ in sorted_tokens[: max(1, top_k)]]


class InMemoryMetadataStore(MetadataStorePort):
    def __init__(self):
        self._db: Dict[Tuple[str, str], MetadataRecord] = {}

    def upsert(self, record: MetadataRecord) -> None:
        self._db[(record.tenant_id, record.metadata_id)] = record

    def get(self, tenant_id: str, metadata_id: str) -> Optional[MetadataRecord]:
        return self._db.get((tenant_id, metadata_id))


class NoopLLMAdapter(LLMAdapterPort):
    def summarize(self, text: str, tenant_id: str) -> str:
        # Very small heuristic summary (first ~40 words)
        words = re.findall(r"\S+", text)
        return " ".join(words[:40])
    def categorize(self, text: str, tenant_id: str, max_labels: int = 5) -> List[str]:
        # Heuristic categories based on keyword presence
        cats = []
        lowered = text.lower()
        if any(k in lowered for k in ("contract", "agreement", "clause", "party")):
            cats.append("legal")
        if any(k in lowered for k in ("invoice", "payment", "amount", "tax")):
            cats.append("finance")
        if any(k in lowered for k in ("meeting", "notes", "minutes", "action")):
            cats.append("meeting-notes")
        return cats[:max_labels]


# --------------------------
# Core service functions
# --------------------------

def _guess_language_simple(text: str) -> str:
    # Very rough heuristic; future: plug langid
    ascii_ratio = sum(1 for ch in text if ord(ch) < 128) / max(1, len(text))
    return "en" if ascii_ratio > 0.85 else "unknown"


def _guess_mime_simple(text: str) -> str:
    # Naive guess for v0.1
    return "text/plain"


def _title_guess(text: str) -> Optional[str]:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line[:120] or None


def _stats(text: str) -> Stats:
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    reading_time_ms = int((words / 200.0) * 60_000)  # 200 wpm baseline
    return Stats(chars=chars, words=words, lines=lines, reading_time_ms=reading_time_ms)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_text_from_input(
    inp: ExtractTextInput | ExtractBlobInput,
    blobs: BlobReaderPort
) -> Tuple[str, int]:
    if isinstance(inp, ExtractTextInput) or inp.kind == "text":
        text = inp.text  # type: ignore[attr-defined]
        size = len(text.encode("utf-8"))
        return text, size
    elif inp.kind == "blob":
        raw = blobs.read(inp.blob_uri)  # type: ignore[attr-defined]
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("latin-1", errors="replace")
        return text, len(raw)
    else:
        raise InvalidInputError(f"Unknown input kind: {getattr(inp, 'kind', None)}")


def build_record(
    text: str,
    size_bytes: int,
    tenant_id: str,
    source_id: Optional[str],
    keyword_extractor: KeywordExtractorPort,
    llm: Optional[LLMAdapterPort],
    llm_enabled: bool,
    top_k: int
) -> MetadataRecord:
    now = datetime.utcnow()
    lang = _guess_language_simple(text)
    mime = _guess_mime_simple(text)
    title = _title_guess(text)
    stats = _stats(text)
    keywords = keyword_extractor.top_keywords(text, top_k=top_k, language_hint=lang)
    hash_hex = _sha256_bytes(text.encode("utf-8"))

    summary = None
    categories: Optional[List[str]] = None

    if llm_enabled and llm is not None:
        with _try_span("llm.extract"):
            try:
                summary = llm.summarize(text, tenant_id)
                categories = llm.categorize(text, tenant_id, max_labels=5)
            except Exception as e:
                logger.exception("LLM extraction failed")
                raise LLMFailedError(str(e))

    return MetadataRecord(
        metadata_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        source_id=source_id,
        hash_sha256=hash_hex,
        size_bytes=size_bytes,
        mime_guess=mime,
        language_guess=lang,
        title=title,
        stats=stats,
        keywords=keywords,
        summary=summary,
        categories=categories,
        created_at=now,
        ingested_at=now,
    )


# --------------------------
# FastAPI Router
# --------------------------

class Dependencies(BaseModel):
    blob_reader: BlobReaderPort = InMemoryBlobReader()
    keyword_extractor: KeywordExtractorPort = SimpleKeywordExtractor()
    store: MetadataStorePort = InMemoryMetadataStore()
    llm: Optional[LLMAdapterPort] = NoopLLMAdapter()


deps_singleton = Dependencies()  # simple DI for v0.1


def get_deps() -> Dependencies:
    return deps_singleton


router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.post("/extract", response_model=Envelope)
def extract(req: ExtractRequest, d: Dependencies = Depends(get_deps)) -> Envelope:
    logger.info("extract.start tenant=%s kind=%s", req.options.tenant_id, req.input.kind)

    with _try_span("metadata.extract"):
        try:
            text, size = _ensure_text_from_input(req.input, d.blob_reader)

            record = build_record(
                text=text,
                size_bytes=size,
                tenant_id=req.options.tenant_id,
                source_id=getattr(req.input, "source_id", None),
                keyword_extractor=d.keyword_extractor,
                llm=d.llm if req.options.llm.enabled else None,
                llm_enabled=req.options.llm.enabled,
                top_k=max(1, req.options.keyword.top_k),
            )

            if req.options.store.persist:
                with _try_span("metadata.persist"):
                    d.store.upsert(record)

            logger.info("extract.done tenant=%s metadata_id=%s", req.options.tenant_id, record.metadata_id)
            return Envelope(ok=True, data=ExtractResponse(record=record))

        except (InvalidInputError, BlobNotFoundError, LLMFailedError, StoreFailedError) as e:
            logger.warning("extract.failed code=%s msg=%s", e.code, str(e))
            raise HTTPException(
                status_code=e.status,
                detail={"code": e.code, "message": str(e)},
            )
        except Exception as e:
            logger.exception("extract.crashed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "metadata.internal_error", "message": str(e)},
            )


@router.get("/{metadata_id}", response_model=Envelope)
def get_metadata(metadata_id: str, tenant_id: str, d: Dependencies = Depends(get_deps)) -> Envelope:
    logger.info("get_metadata tenant=%s id=%s", tenant_id, metadata_id)
    with _try_span("metadata.get"):
        rec = d.store.get(tenant_id=tenant_id, metadata_id=metadata_id)
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "metadata.not_found", "message": "Record not found"},
            )
        return Envelope(ok=True, data=rec)


# Optional: mountable FastAPI app
def create_app() -> FastAPI:
    app = FastAPI(title="MetadataService")
    app.include_router(router)
    return app

---

```python
