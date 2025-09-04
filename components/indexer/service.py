from __future__ import annotations
from typing import Dict, Any, List
import logging

from .contracts import ChunkerPort, EmbedderPort, VectorStorePort, JobStorePort, VectorItem
from .schemas import CreateIndexJobRequest, JobStatus
from .errors import ValidationError, NotFoundError, VectorStoreError
from datetime import datetime

log = logging.getLogger("indexer.service")


class IndexerService:
    """
    Orchestrates the indexing pipeline: validate → chunk → embed → upsert → update job status/events.
    First iteration processes synchronously (no background workers).
    """

    def __init__(self, *, chunker: ChunkerPort, embedder: EmbedderPort, vector_store: VectorStorePort, job_store: JobStorePort):
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.job_store = job_store

    # ------------------------
    # API (used by routes)
    # ------------------------
    def create_job(self, payload: CreateIndexJobRequest) -> str:
        self._validate_payload(payload)
        job_id = self.job_store.create_job(payload.tenant_id)
        log.info("job_created job_id=%s tenant_id=%s", job_id, payload.tenant_id)
        self.job_store.set_status(job_id, "running")

        try:
            # Determine text source
            text = payload.doc.text
            if not text:
                if payload.doc.blob_uri:
                    # Stub for now – next iteration: use BlobStorageAdapter + extraction
                    log.warning("blob_uri_provided_but_no_extractor_yet uri=%s", payload.doc.blob_uri)
                    raise ValidationError("Text is required in first iteration (blob extraction not yet implemented).")
                else:
                    raise ValidationError("Either 'text' or 'blob_uri' must be provided.")

            doc_meta = dict(payload.doc.metadata or {})
            doc_meta.update(
                {
                    "doc_id": payload.doc.doc_id,
                    "fingerprint": payload.doc.fingerprint,
                    "tenant_id": payload.tenant_id,
                }
            )

            # Chunk
            self.job_store.add_event(job_id, "chunking_started", {"chunk_size": payload.options.chunk_size, "overlap": payload.options.chunk_overlap})
            chunks = self.chunker.chunk(
                text,
                chunk_size=payload.options.chunk_size,
                chunk_overlap=payload.options.chunk_overlap,
                doc_meta=doc_meta,
            )
            self.job_store.add_event(job_id, "chunking_completed", {"count": len(chunks)})
            self.job_store.inc_counts(job_id, chunks_total=len(chunks))
            log.info("chunking_completed job_id=%s count=%d", job_id, len(chunks))

            if not chunks:
                self.job_store.add_event(job_id, "job_completed", {"reason": "no_chunks"})
                self.job_store.set_status(job_id, "completed")
                return job_id

            # Embed
            self.job_store.add_event(job_id, "embedding_started", {"batch": len(chunks)})
            embeddings = self.embedder.embed_texts([c.text for c in chunks])
            self.job_store.add_event(job_id, "embedding_completed", {"count": len(embeddings)})
            log.info("embedding_completed job_id=%s count=%d", job_id, len(embeddings))

            # Build vector items
            ns = self._namespace(payload.tenant_id, payload.options.vector_namespace)
            items: List[VectorItem] = []
            for c, vec in zip(chunks, embeddings):
                item_id = self._make_item_id(payload, c)
                meta = dict(c.metadata)
                meta["job_id"] = job_id
                items.append(
                    VectorItem(
                        id=item_id,
                        values=list(vec),
                        metadata=meta,
                    )
                )

            # Upsert
            self.job_store.add_event(job_id, "upsert_started", {"namespace": ns, "count": len(items)})
            self.vector_store.upsert(namespace=ns, items=items)
            self.job_store.add_event(job_id, "upsert_completed", {"count": len(items)})
            self.job_store.inc_counts(job_id, chunks_indexed=len(items))
            log.info("upsert_completed job_id=%s namespace=%s count=%d", job_id, ns, len(items))

            # Done
            self.job_store.add_event(job_id, "job_completed", {})
            self.job_store.set_status(job_id, "completed")
            return job_id

        except ValidationError as ve:
            self.job_store.add_error(job_id, f"validation:{ve}")
            self.job_store.set_status(job_id, "failed")
            log.exception("job_failed_validation job_id=%s", job_id)
            return job_id
        except Exception as ex:
            self.job_store.add_error(job_id, f"internal:{ex}")
            self.job_store.set_status(job_id, "failed")
            log.exception("job_failed_internal job_id=%s")
            return job_id

    def get_job(self, job_id: str) -> JobStatus:
        data = self.job_store.get_status(job_id)
        return JobStatus.model_validate(data)

    def list_events(self, job_id: str):
        evs = self.job_store.list_events(job_id)
        return evs

    # ------------------------
    # Helpers
    # ------------------------
    def _validate_payload(self, payload: CreateIndexJobRequest) -> None:
        if not payload.tenant_id:
            raise ValidationError("tenant_id is required.")
        if not (payload.doc.text or payload.doc.blob_uri):
            raise ValidationError("Either doc.text or doc.blob_uri must be provided.")

    def _namespace(self, tenant_id: str, maybe_ns: str | None) -> str:
        ns = maybe_ns or "default"
        return f"{tenant_id}:{ns}"

    def _make_item_id(self, payload: CreateIndexJobRequest, chunk) -> str:
        # deterministic ID: doc_id or fallback + chunk idx
        base = payload.doc.doc_id or payload.doc.fingerprint or "doc"
        return f"{base}:{chunk.idx}"


