```md
# BlobStorageAdapter — Contract-Driven Spec (lbp3-rs)

> Priority: Testability & Observability. Internals are swappable behind a stable port.

## 1. Purpose
Provide a uniform interface for storing, retrieving, listing, and deleting binary blobs, supporting:
- Local filesystem (dev/test)
- S3-compatible object storage (prod)
- (Future) GCS/Azure/Fileblob

## 2. Responsibilities
- Put/Get/Delete blobs by `{tenant_id}/{bucket}/{key}`
- Stream reads/writes to handle large files
- List blobs with pagination & simple prefix filtering
- Generate pre-signed URLs for direct client uploads/downloads (when backend supports it)
- Content hashing (sha256) and ETag handling where available
- Enforce tenant isolation
- Emit structured logs, trace spans, and return UWF responses on the service façade

## 3. Non-Responsibilities
- Authentication/Authorization (delegated to AuthService/gateways)
- Business metadata (delegated to MetadataService)
- Virus scanning / PII scrub (hook points are exposed, not implemented here)

## 4. Contracts (see `contracts.py`)
- **Models**: `BlobRef`, `BlobMeta`, `PutBlobRequest/Result`, `GetBlobRequest/Result`, `DeleteBlobRequest/Result`,  
  `ListBlobsRequest/Result`, `PresignRequest/Result`, `HeadBlobResult`, `UWFResponse`, `ErrorPayload`, …
- **Error codes**: `VALIDATION`, `NOT_FOUND`, `CONFLICT`, `UPSTREAM`, `INTERNAL`
- **Binary streaming**: iterator of `bytes` for reads; write accepts `bytes | Iterable[bytes]`

## 5. Ports (see `ports.py`)
`BlobStoragePort` (async) with:
- `put_blob(req) -> PutBlobResult`
- `get_blob_stream(req) -> AsyncIterator[bytes]`
- `head_blob(ref) -> HeadBlobResult`
- `delete_blob(req) -> DeleteBlobResult`
- `list_blobs(req) -> ListBlobsResult`
- `create_presigned_url(req) -> PresignResult | None`

Adapters:
- `LocalFSBlobAdapter`
- `S3BlobAdapter`

## 6. Observability
- Structured logs on each op (tenant, bucket, key, bytes, duration)
- OpenTelemetry spans (if OTEL installed): `blob.put`, `blob.get`, `blob.head`, `blob.delete`, `blob.list`, `blob.presign`
- Trace attributes: `tenant_id`, `bucket`, `key`, `adapter`, `size`, `status`
- Correlate with `trace_id` in UWF `meta`

## 7. Configuration (see `config.py`)
- `BLOB_ADAPTER`: `"localfs"` | `"s3"`
- Local: `BLOB_LOCAL_ROOT`
- S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_DEFAULT`, `S3_ENDPOINT_URL?`, `S3_FORCE_PATH_STYLE?`

## 8. Testing
- Pytest tests for LocalFS adapter using temporary directories
- Golden path: put → head → get → list → delete
- Error path: get/delete missing → NOT_FOUND

## 9. Security & Multitenancy
- Tenant isolation via path/bucket prefixes
- No traversal: normalize keys to prevent `..` escaping
- Max size checks (optional future: via config/policy hook)

## 10. TODO (next iterations)
- [ ] Add size/type enforcement hooks (+ plan tiers)
- [ ] E2E integration with ApiGateway and AuthService via FastAPI routes
- [ ] GCS/Azure adapters
- [ ] Server-side encryption options
- [ ] Parallel multipart uploads for large files (S3)
- [ ] Quotas & metrics export (Prometheus)
- [ ] Retry policy/backoff wrapper for transient errors

---

### 2) Contracts
