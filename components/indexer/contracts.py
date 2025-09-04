from __future__ import annotations
from dataclasses import dataclass
from typing import List, Protocol, Sequence, Dict, Any, Iterable, Optional


@dataclass
class Chunk:
    doc_id: Optional[str]
    idx: int
    text: str
    metadata: Dict[str, Any]


@dataclass
class VectorItem:
    id: str
    values: List[float]
    metadata: Dict[str, Any]


class ChunkerPort(Protocol):
    def chunk(self, text: str, *, chunk_size: int, chunk_overlap: int, doc_meta: Dict[str, Any]) -> List[Chunk]:
        ...


class EmbedderPort(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        ...


class VectorStorePort(Protocol):
    def upsert(self, *, namespace: str, items: Iterable[VectorItem]) -> None:
        ...


class JobStorePort(Protocol):
    # Minimal job/event persistence for first pass
    def create_job(self, tenant_id: str) -> str: ...
    def set_status(self, job_id: str, status: str) -> None: ...
    def get_status(self, job_id: str) -> Dict[str, Any]: ...
    def add_event(self, job_id: str, event_type: str, data: Dict[str, Any]) -> None: ...
    def inc_counts(self, job_id: str, **kwargs: int) -> None: ...
    def add_error(self, job_id: str, msg: str) -> None: ...
    def list_events(self, job_id: str) -> List[Dict[str, Any]]: ...


