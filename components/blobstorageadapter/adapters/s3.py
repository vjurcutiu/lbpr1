
from __future__ import annotations
import asyncio
import hashlib
import time
from typing import AsyncIterator, Optional

try:
    import boto3
    from botocore.client import Config as BotoConfig
    from botocore.exceptions import ClientError
except Exception:  # pragma: no cover
    boto3 = None
    ClientError = Exception
    BotoConfig = object  # type: ignore

from ..contracts import (
    BlobRef, BlobMeta, PutBlobRequest, PutBlobResult, GetBlobRequest, GetBlobResult,
    DeleteBlobRequest, DeleteBlobResult, ListBlobsRequest, ListBlobsResult, BlobItem,
    HeadBlobResult, PresignRequest, PresignResult
)
from ..errors import BlobNotFound, BlobConflict, BlobValidation, BlobUpstream
from ..ports import BlobStoragePort

class S3BlobAdapter(BlobStoragePort):
    def __init__(self, bucket_default: str, region: Optional[str] = None,
                 endpoint_url: Optional[str] = None, force_path_style: bool = False):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3BlobAdapter")
        self.s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=BotoConfig(s3={"addressing_style": "path" if force_path_style else "auto"})
        )
        self.bucket_default = bucket_default
        self.adapter = "s3"

    def _bucket(self, tenant_id: str, bucket: str) -> str:
        # Strategy: single physical bucket with logical prefixes OR per-tenant bucket.
        # For now, use a single default bucket and put tenant/bucket as prefix.
        return self.bucket_default

    def _key(self, ref: BlobRef) -> str:
        # logical prefix: tenant_id/bucket/key
        k = "/".join([ref.tenant_id.strip("/"), ref.bucket.strip("/"), ref.key.strip("/")])
        if ".." in k:
            raise BlobValidation("invalid key")
        return k

    async def put_blob(self, req: PutBlobRequest) -> PutBlobResult:
        ref = req.ref
        bucket = self._bucket(ref.tenant_id, ref.bucket)
        key = self._key(ref)

        kwargs = {"Bucket": bucket, "Key": key}
        if req.content_type:
            kwargs["ContentType"] = req.content_type

        if not req.overwrite:
            # use If-None-Match to avoid overwrite
            kwargs["ExpectedBucketOwner"] = None  # no-op; ETag-based conditional put not trivial here
            # We simulate: first check head
            try:
                await asyncio.to_thread(self.s3.head_object, Bucket=bucket, Key=key)
                raise BlobConflict("blob exists and overwrite=False")
            except ClientError as e:
                if e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                    pass  # either not found or another error; continue for upload

        body = None
        if req.data is not None:
            body = req.data
        elif req.chunks is not None:
            # stream upload: combine in-memory for first iteration; TODO: multipart upload
            body = b"".join(req.chunks)
        else:
            raise BlobValidation("either data or chunks must be provided")

        etag = None
        sha256_hex = None
        if req.compute_sha256:
            sha256_hex = hashlib.sha256(body).hexdigest()

        def upload():
            resp = self.s3.put_object(Body=body, **kwargs)
            return resp.get("ETag")

        etag = await asyncio.to_thread(upload)

        meta = BlobMeta(size=len(body), content_type=req.content_type, etag=etag, sha256=sha256_hex)
        return PutBlobResult(ref=ref, meta=meta)

    async def get_blob_stream(self, req: GetBlobRequest):
        ref = req.ref
        bucket = self._bucket(ref.tenant_id, ref.bucket)
        key = self._key(ref)

        get_kwargs = {"Bucket": bucket, "Key": key}
        if req.range_start is not None or req.range_end is not None:
            start = req.range_start or 0
            end = "" if req.range_end is None else req.range_end
            get_kwargs["Range"] = f"bytes={start}-{end}"

        try:
            obj = await asyncio.to_thread(self.s3.get_object, **get_kwargs)
        except ClientError as e:
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 or status == 416:
                raise BlobNotFound("blob not found")
            raise BlobUpstream(str(e))

        stream = obj["Body"]

        # yield in chunks from the streaming body
        while True:
            data = await asyncio.to_thread(stream.read, 64 * 1024)
            if not data:
                break
            yield data

    async def head_blob(self, ref) -> HeadBlobResult:
        bucket = self._bucket(ref.tenant_id, ref.bucket)
        key = self._key(ref)
        try:
            resp = await asyncio.to_thread(self.s3.head_object, Bucket=bucket, Key=key)
        except ClientError as e:
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                raise BlobNotFound("blob not found")
            raise BlobUpstream(str(e))

        size = int(resp.get("ContentLength", 0))
        etag = resp.get("ETag")
        ct = resp.get("ContentType")
        return HeadBlobResult(ref=ref, meta=BlobMeta(size=size, content_type=ct, etag=etag))

    async def delete_blob(self, req: DeleteBlobRequest) -> DeleteBlobResult:
        bucket = self._bucket(req.ref.tenant_id, req.ref.bucket)
        key = self._key(req.ref)
        try:
            await asyncio.to_thread(self.s3.delete_object, Bucket=bucket, Key=key)
        except ClientError as e:
            status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404 and req.missing_ok:
                return DeleteBlobResult(ref=req.ref, deleted=False)
            if status == 404:
                raise BlobNotFound("blob not found")
            raise BlobUpstream(str(e))
        return DeleteBlobResult(ref=req.ref, deleted=True)

    async def list_blobs(self, req: ListBlobsRequest) -> ListBlobsResult:
        bucket = self._bucket(req.tenant_id, req.bucket)
        prefix = "/".join([req.tenant_id.strip("/"), req.bucket.strip("/"), req.prefix.strip("/")]).strip("/")
        kwargs = {"Bucket": bucket, "Prefix": prefix or None, "MaxKeys": req.limit}
        if req.cursor:
            kwargs["ContinuationToken"] = req.cursor

        try:
            resp = await asyncio.to_thread(self.s3.list_objects_v2, **kwargs)
        except ClientError as e:
            raise BlobUpstream(str(e))

        contents = resp.get("Contents", []) or []
        items = []
        for c in contents:
            full_key = c["Key"]
            # strip logical prefix back to "key"
            logical_prefix = f"{req.tenant_id}/{req.bucket}/"
            if not full_key.startswith(logical_prefix):
                continue
            key = full_key[len(logical_prefix):]
            items.append(BlobItem(key=key, meta=BlobMeta(size=int(c.get("Size", 0)), etag=c.get("ETag"))))

        next_cursor = resp.get("NextContinuationToken")
        return ListBlobsResult(tenant_id=req.tenant_id, bucket=req.bucket, items=items, next_cursor=next_cursor)

    async def create_presigned_url(self, req: PresignRequest) -> Optional[PresignResult]:
        bucket = self._bucket(req.ref.tenant_id, req.ref.bucket)
        key = self._key(req.ref)
        method = "put_object" if req.op == "upload" else "get_object"
        params = {"Bucket": bucket, "Key": key}
        if req.op == "upload" and req.content_type:
            params["ContentType"] = req.content_type

        try:
            url = await asyncio.to_thread(
                self.s3.generate_presigned_url, ClientMethod=method, Params=params, ExpiresIn=req.expires_seconds
            )
        except ClientError as e:
            raise BlobUpstream(str(e))

        expires_at = int(time.time()) + int(req.expires_seconds)
        return PresignResult(url=url, method="PUT" if req.op == "upload" else "GET", headers={}, expires_at_epoch_s=expires_at)

### 8) Service façade (UWF + logging/otel)
