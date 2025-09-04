from __future__ import annotations
from typing import Dict, Any, List, Iterable, Sequence, Optional
from datetime import datetime, timezone
import hashlib
import logging

from .contracts import JobStorePort, VectorStorePort, VectorItem, ChunkerPort, Chunk, EmbedderPort

log = logging.getLogger("indexer.adapters")


# ------------------------
# In-memory JobStore
# ------------------------
class InMemoryJobStore(JobStorePort):
    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, List[Dict[str, Any]]] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_job(self, tenant_id: str) -> str:
        job_id = f"idx_{hashlib.sha1((tenant_id+str(self._now())).encode()).hexdigest()[:10]}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "pending",
            "created_at": self._now(),
            "updated_at": self._now(),
            "counts": {"chunks_total": 0, "chunks_indexed": 0, "errors": 0},
            "errors": [],
        }
        self._events[job_id] = []
        return job_id

    def set_status(self, job_id: str, status: str) -> None:
        self._jobs[job_id]["status"] = status
        self._jobs[job_id]["updated_at"] = self._now()

    def get_status(self, job_id: str) -> Dict[str, Any]:
        return self._jobs[job_id]

    def add_event(self, job_id: str, event_type: str, data: Dict[str, Any]) -> None:
        evt = {"ts": self._now(), "type": event_type, "data": data}
        self._events[job_id].append(evt)
        self._jobs[job_id]["updated_at"] = self._now()

    def inc_counts(self, job_id: str, **kwargs: int) -> None:
        for k, v in kwargs.items():
            self._jobs[job_id]["counts"][k] += int(v)
        self._jobs[job_id]["updated_at"] = self._now()

    def add_error(self, job_id: str, msg: str) -> None:
        self._jobs[job_id]["errors"].append(msg)
        self._jobs[job_id]["counts"]["errors"] += 1
        self._jobs[job_id]["updated_at"] = self._now()

    def list_events(self, job_id: str) -> List[Dict[str, Any]]:
        return list(self._events[job_id])


# ------------------------
# In-memory VectorStore
# ------------------------
class InMemoryVectorStore(VectorStorePort):
    def __init__(self) -> None:
        # keyed by namespace -> id -> VectorItem
        self._db: Dict[str, Dict[str, VectorItem]] = {}

    def upsert(self, *, namespace: str, items: Iterable[VectorItem]) -> None:
        ns = self._db.setdefault(namespace, {})
        count = 0
        for it in items:
            ns[it.id] = it
            count += 1
        log.info("vector_upsert_completed namespace=%s count=%d", namespace, count)


# ------------------------
# Simple chunker
# ------------------------
class SimpleChunker(ChunkerPort):
    def chunk(self, text: str, *, chunk_size: int, chunk_overlap: int, doc_meta: Dict[str, Any]) -> List[Chunk]:
        words = text.split()
        chunks: List[Chunk] = []
        if not words:
            return chunks

        step = max(1, chunk_size - chunk_overlap)
        idx = 0
        i = 0
        while i < len(words):
            window = words[i : i + chunk_size]
            chunk_text = " ".join(window)
            chunks.append(
                Chunk(
                    doc_id=doc_meta.get("doc_id"),
                    idx=idx,
                    text=chunk_text,
                    metadata={**doc_meta, "chunk_idx": idx},
                )
            )
            idx += 1
            i += step
        return chunks


# ------------------------
# Dummy embedder
# ------------------------
class DummyEmbedder(EmbedderPort):
    """
    Deterministic, fast embedder for tests: hashes text to floats in [0,1).
    Shape: 16-dim vector.
    """
    def __init__(self, dim: int = 16) -> None:
        self.dim = dim

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        vecs: List[List[float]] = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            # Take first `dim` bytes and map to floats
            v = [b / 255.0 for b in h[: self.dim]]
            vecs.append(v)
        return vecs


