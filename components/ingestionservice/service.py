from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

from .contracts import (
    CreateIngestionRequest,
    IngestionEvent,
    IngestionItem,
    IngestionJob,
    IngestionStatus,
)
from .errors import AdapterError, BadRequestError
from .ports import BlobStorageAdapterPort, IndexerPort, MetadataServicePort
from .repository import InMemoryIngestionRepo


class IngestionService:
    """
    Orchestrates: validate -> store blobs -> upsert metadata -> submit to Indexer
    Tracks job status and append-only events for observability.
    """

    def __init__(
        self,
        tenant_id: str,
        repo: InMemoryIngestionRepo,
        blob: BlobStorageAdapterPort,
        meta: MetadataServicePort,
        indexer: IndexerPort,
    ) -> None:
        self.tenant_id = tenant_id
        self.repo = repo
        self.blob = blob
        self.meta = meta
        self.indexer = indexer

    def _event(self, type_: str, message: str, data: Optional[Dict[str, Any]] = None) -> IngestionEvent:
        return IngestionEvent(type=type_, message=message, ts=time.time(), data=data or {})

    def create_ingestion(self, req: CreateIngestionRequest) -> IngestionJob:
        if req.total_items() == 0:
            raise BadRequestError("No items supplied: provide files, file_refs, or source_urls.")

        job = self.repo.create_job(self.tenant_id)
        self.repo.append_event(job, self._event("job.created", "Ingestion job created."))

        # Move to RUNNING
        job.status = IngestionStatus.RUNNING
        self.repo.save_job(job)
        self.repo.append_event(job, self._event("job.running", "Processing items."))

        items: List[IngestionItem] = []

        # 1) Inline files -> store into blob
        for f in req.files or []:
            try:
                raw = base64.b64decode(f.bytes_b64)
            except Exception as e:
                job.status = IngestionStatus.FAILED
                self.repo.save_job(job)
                self.repo.append_event(job, self._event("file.decode_failed", "Base64 decode failed", {"filename": f.filename, "error": str(e)}))
                return job

            try:
                blob_uri = self.blob.put_bytes(
                    tenant_id=self.tenant_id, path_hint=f.filename, raw=raw, content_type=f.content_type
                )
            except Exception as e:
                job.status = IngestionStatus.FAILED
                self.repo.save_job(job)
                self.repo.append_event(job, self._event("blob.put_failed", "Blob storage put failed", {"filename": f.filename, "error": str(e)}))
                return job

            size_bytes = len(raw)
            try:
                metadata_id = self.meta.upsert_file(
                    tenant_id=self.tenant_id,
                    blob_uri=blob_uri,
                    filename=f.filename,
                    content_type=f.content_type,
                    size_bytes=size_bytes,
                    extra=None,
                )
            except Exception as e:
                job.status = IngestionStatus.FAILED
                self.repo.save_job(job)
                self.repo.append_event(job, self._event("metadata.upsert_failed", "Metadata upsert failed", {"filename": f.filename, "blob_uri": blob_uri, "error": str(e)}))
                return job

            item = IngestionItem(
                kind="inline_file",
                filename=f.filename,
                blob_uri=blob_uri,
                content_type=f.content_type,
                size_bytes=size_bytes,
                metadata_id=metadata_id,
            )
            items.append(item)
            self.repo.append_event(job, self._event("file.ingested", "Inline file ingested", item.dict()))

        # 2) File refs (already in blob)
        for r in req.file_refs or []:
            try:
                metadata_id = self.meta.upsert_file(
                    tenant_id=self.tenant_id,
                    blob_uri=r.blob_uri,
                    filename=r.filename,
                    content_type=r.content_type,
                    size_bytes=-1,  # unknown
                    extra={"from": "file_ref"},
                )
            except Exception as e:
                job.status = IngestionStatus.FAILED
                self.repo.save_job(job)
                self.repo.append_event(job, self._event("metadata.upsert_failed", "Metadata upsert failed", {"filename": r.filename, "blob_uri": r.blob_uri, "error": str(e)}))
                return job

            item = IngestionItem(
                kind="file_ref",
                filename=r.filename,
                blob_uri=r.blob_uri,
                content_type=r.content_type,
                size_bytes=None,
                metadata_id=metadata_id,
            )
            items.append(item)
            self.repo.append_event(job, self._event("file.ref_registered", "File ref registered", item.dict()))

        # 3) URLs (future hook: remote fetcher)
        for u in req.source_urls or []:
            item = IngestionItem(kind="url", filename=None, blob_uri=str(u), content_type=None, size_bytes=None, metadata_id=None)
            items.append(item)
            self.repo.append_event(job, self._event("url.accepted", "URL accepted (fetch not implemented)", {"url": str(u)}))

        job.items = items
        self.repo.save_job(job)

        # 4) Submit to Indexer
        try:
            index_items: List[Dict[str, Any]] = []
            for it in items:
                if it.blob_uri:
                    index_items.append(
                        {
                            "blob_uri": it.blob_uri,
                            "metadata_id": it.metadata_id,
                            "filename": it.filename,
                            "content_type": it.content_type,
                            "size_bytes": it.size_bytes,
                        }
                    )
            index_job_id = self.indexer.create_job(self.tenant_id, index_items)
        except Exception as e:
            job.status = IngestionStatus.FAILED
            self.repo.save_job(job)
            self.repo.append_event(job, self._event("indexer.create_failed", "Indexer job creation failed", {"error": str(e)}))
            return job

        job.index_job_id = index_job_id
        job.status = IngestionStatus.SUBMITTED_TO_INDEXER
        self.repo.save_job(job)
        self.repo.append_event(job, self._event("indexer.submitted", "Submitted to indexer", {"index_job_id": index_job_id}))

        # v0.1 stops here — indexer completion will update status later (future integration).
        return job

    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        return self.repo.get_job(self.tenant_id, job_id)

    def list_events(self, job_id: str):
        return self.repo.list_events(self.tenant_id, job_id)


