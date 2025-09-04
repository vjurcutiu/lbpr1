"""
MetadataService Contracts & Ports (v0.1)

Project: lbp3-rs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable
from pydantic import BaseModel, Field, HttpUrl, constr


# --------------------------
# UWF-ish Envelope
# --------------------------

class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class Envelope(BaseModel):
    ok: bool = True
    data: Optional[Any] = None
    error: Optional[ErrorEnvelope] = None


# --------------------------
# Domain Models
# --------------------------

class InputKind(str):
    TEXT = "text"
    BLOB = "blob"


class ExtractTextInput(BaseModel):
    kind: constr(strip_whitespace=True, to_lower=True) = InputKind.TEXT
    text: str = Field(..., min_length=1)
    source_id: Optional[str] = None


class ExtractBlobInput(BaseModel):
    kind: constr(strip_whitespace=True, to_lower=True) = InputKind.BLOB
    blob_uri: str = Field(..., description="URI understood by BlobStorageAdapter")
    source_id: Optional[str] = None


class LLMOptions(BaseModel):
    enabled: bool = False
    # room for provider/model/options later
    summary: bool = True
    categories: bool = True


class KeywordOptions(BaseModel):
    top_k: int = 10


class StoreOptions(BaseModel):
    persist: bool = True


class ExtractOptions(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    llm: LLMOptions = LLMOptions()
    keyword: KeywordOptions = KeywordOptions()
    store: StoreOptions = StoreOptions()


class ExtractRequest(BaseModel):
    input: ExtractTextInput | ExtractBlobInput
    options: ExtractOptions


class Stats(BaseModel):
    chars: int
    words: int
    lines: int
    reading_time_ms: int


class MetadataRecord(BaseModel):
    metadata_id: str
    tenant_id: str
    source_id: Optional[str] = None

    hash_sha256: str
    size_bytes: int
    mime_guess: str
    language_guess: str
    title: Optional[str] = None

    stats: Stats
    keywords: List[str] = []
    summary: Optional[str] = None
    categories: Optional[List[str]] = None

    created_at: datetime
    ingested_at: datetime


class ExtractResponse(BaseModel):
    record: MetadataRecord


# --------------------------
# Ports (Protocols)
# --------------------------

@runtime_checkable
class BlobReaderPort(Protocol):
    def read(self, blob_uri: str) -> bytes:
        ...


@runtime_checkable
class LLMAdapterPort(Protocol):
    def summarize(self, text: str, tenant_id: str) -> str:
        ...
    def categorize(self, text: str, tenant_id: str, max_labels: int = 5) -> List[str]:
        ...


@runtime_checkable
class MetadataStorePort(Protocol):
    def upsert(self, record: MetadataRecord) -> None:
        ...
    def get(self, tenant_id: str, metadata_id: str) -> Optional[MetadataRecord]:
        ...


@runtime_checkable
class KeywordExtractorPort(Protocol):
    def top_keywords(self, text: str, top_k: int = 10, language_hint: Optional[str] = None) -> List[str]:
        ...


# --------------------------
# Errors
# --------------------------

class MetadataError(Exception):
    code: str = "metadata.internal_error"
    status: int = 500

    def envelope(self, message: str, details: Optional[Dict[str, Any]] = None) -> Envelope:
        return Envelope(ok=False, error=ErrorEnvelope(code=self.code, message=message, details=details))


class InvalidInputError(MetadataError):
    code = "metadata.invalid_input"
    status = 400


class BlobNotFoundError(MetadataError):
    code = "metadata.blob_not_found"
    status = 404


class LLMFailedError(MetadataError):
    code = "metadata.llm_failed"
    status = 502


class StoreFailedError(MetadataError):
    code = "metadata.store_failed"
    status = 500
````

---

```python
