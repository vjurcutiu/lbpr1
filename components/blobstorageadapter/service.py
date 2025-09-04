
from __future__ import annotations
import logging
import time
from contextlib import contextmanager
from typing import AsyncIterator, Optional

from .contracts import (
    UWFResponse, ErrorPayload, MetaPayload, BlobRef, PutBlobRequest, GetBlobRequest,
    DeleteBlobRequest, ListBlobsRequest, PresignRequest
)
from .errors import BlobNotFound, BlobConflict, BlobValidation, BlobUpstream, BlobInternal
from .ports import BlobStoragePort

log = logging.getLogger("blobstorage")

# Optional OpenTelemetry
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("blobstorage")
except Exception:  # pragma: no cover
    tracer = None

@contextmanager
def _span(name: str, **attrs):
    if tracer:
        with tracer.start_as_current_span(name) as span:
            for k, v in attrs.items():
                try:
                    span.set_attribute(f"blob.{k}", v)
                except Exception:
                    pass
            yield
    else:
        yield

def _uwf_ok(result, meta: MetaPayload) -> UWFResponse:
    return UWFResponse(ok=True, result=result, meta=meta)

def _uwf_err(e: Exception, meta: MetaPayload) -> UWFResponse:
    if isinstance(e, BlobValidation):
        t, code = "VALIDATION", "BLOB_VALIDATION"
    elif isinstance(e, BlobNotFound):
        t, code = "NOT_FOUND", "BLOB_NOT_FOUND"
    elif isinstance(e, BlobConflict):
        t, code = "CONFLICT", "BLOB_CONFLICT"
    elif isinstance(e, BlobUpstream):
        t, code = "UPSTREAM", "BLOB_UPSTREAM"
    else:
        t, code = "INTERNAL", "BLOB_INTERNAL"

    err = ErrorPayload(type=t, code=code, message=str(e))
    return UWFResponse(ok=False, error=err, meta=meta)

class BlobService:
    def __init__(self, adapter: BlobStoragePort, adapter_name: str):
        self.adapter = adapter
        self.adapter_name = adapter_name

    async def put(self, req: PutBlobRequest) -> UWFResponse:
        t0 = time.time()
        meta = MetaPayload(tenant_id=req.ref.ref if hasattr(req.ref, "tenant_id") else None, adapter=self.adapter_name)
        with _span("blob.put", tenant_id=req.ref.tenant_id, bucket=req.ref.bucket, key=req.ref.key, adapter=self.adapter_name):
            try:
                res = await self.adapter.put_blob(req)
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.info("blob.put ok tenant=%s bucket=%s key=%s size=%s adapter=%s dur_ms=%s",
                         req.ref.tenant_id, req.ref.bucket, req.ref.key, res.meta.size, self.adapter_name, meta.duration_ms)
                return _uwf_ok(res.dict(), meta)
            except Exception as e:
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.exception("blob.put err tenant=%s bucket=%s key=%s adapter=%s dur_ms=%s",
                              req.ref.tenant_id, req.ref.bucket, req.ref.key, self.adapter_name, meta.duration_ms)
                return _uwf_err(e, meta)

    async def head(self, ref: BlobRef) -> UWFResponse:
        t0 = time.time()
        meta = MetaPayload(tenant_id=ref.tenant_id, adapter=self.adapter_name)
        with _span("blob.head", tenant_id=ref.tenant_id, bucket=ref.bucket, key=ref.key, adapter=self.adapter_name):
            try:
                res = await self.adapter.head_blob(ref)
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.info("blob.head ok tenant=%s bucket=%s key=%s size=%s", ref.tenant_id, ref.bucket, ref.key, res.meta.size)
                return _uwf_ok(res.dict(), meta)
            except Exception as e:
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.exception("blob.head err tenant=%s bucket=%s key=%s", ref.tenant_id, ref.bucket, ref.key)
                return _uwf_err(e, meta)

    async def delete(self, req: DeleteBlobRequest) -> UWFResponse:
        t0 = time.time()
        meta = MetaPayload(tenant_id=req.ref.tenant_id, adapter=self.adapter_name)
        with _span("blob.delete", tenant_id=req.ref.tenant_id, bucket=req.ref.bucket, key=req.ref.key, adapter=self.adapter_name):
            try:
                res = await self.adapter.delete_blob(req)
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.info("blob.delete ok tenant=%s bucket=%s key=%s deleted=%s", req.ref.tenant_id, req.ref.bucket, req.ref.key, res.deleted)
                return _uwf_ok(res.dict(), meta)
            except Exception as e:
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.exception("blob.delete err tenant=%s bucket=%s key=%s", req.ref.tenant_id, req.ref.bucket, req.ref.key)
                return _uwf_err(e, meta)

    async def list(self, req: ListBlobsRequest) -> UWFResponse:
        t0 = time.time()
        meta = MetaPayload(tenant_id=req.tenant_id, adapter=self.adapter_name)
        with _span("blob.list", tenant_id=req.tenant_id, bucket=req.bucket, prefix=req.prefix, adapter=self.adapter_name):
            try:
                res = await self.adapter.list_blobs(req)
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.info("blob.list ok tenant=%s bucket=%s count=%s", req.tenant_id, req.bucket, len(res.items))
                return _uwf_ok(res.dict(), meta)
            except Exception as e:
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.exception("blob.list err tenant=%s bucket=%s", req.tenant_id, req.bucket)
                return _uwf_err(e, meta)

    async def presign(self, req: PresignRequest) -> UWFResponse:
        t0 = time.time()
        meta = MetaPayload(tenant_id=req.ref.tenant_id, adapter=self.adapter_name)
        with _span("blob.presign", tenant_id=req.ref.tenant_id, bucket=req.ref.bucket, key=req.ref.key, op=req.op, adapter=self.adapter_name):
            try:
                res = await self.adapter.create_presigned_url(req)
                meta.duration_ms = int((time.time() - t0) * 1000)
                if res is None:
                    log.info("blob.presign unsupported adapter=%s", self.adapter_name)
                    return _uwf_ok(None, meta)
                log.info("blob.presign ok tenant=%s bucket=%s key=%s", req.ref.tenant_id, req.ref.bucket, req.ref.key)
                return _uwf_ok(res.dict(), meta)
            except Exception as e:
                meta.duration_ms = int((time.time() - t0) * 1000)
                log.exception("blob.presign err tenant=%s bucket=%s key=%s", req.ref.tenant_id, req.ref.bucket, req.ref.key)
                return _uwf_err(e, meta)

### 9) `__init__` + simple factory
