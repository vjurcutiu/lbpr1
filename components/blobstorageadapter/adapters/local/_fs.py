
from __future__ import annotations
import asyncio
import hashlib
import os
from pathlib import Path
from typing import AsyncIterator, Optional, Iterable

from ..contracts import (
    BlobRef, BlobMeta, PutBlobRequest, PutBlobResult, GetBlobRequest, GetBlobResult,
    DeleteBlobRequest, DeleteBlobResult, ListBlobsRequest, ListBlobsResult, BlobItem,
    HeadBlobResult, PresignRequest, PresignResult
)
from ..errors import BlobNotFound, BlobConflict, BlobValidation
from ..ports import BlobStoragePort

def _safe_join(root: Path, *parts: str) -> Path:
    p = root
    for part in parts:
        # basic traversal guard
        part = part.strip("/\\")
        if ".." in part:
            raise BlobValidation("invalid key (traversal detected)")
        p = p / part
    return p.resolve()

class LocalFSBlobAdapter(BlobStoragePort):
    def __init__(self, root_dir: str):
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.adapter = "localfs"

    def _path_for(self, ref: BlobRef) -> Path:
        return _safe_join(self.root, ref.tenant_id, ref.bucket, ref.key)

    async def put_blob(self, req: PutBlobRequest) -> PutBlobResult:
        ref = req.ref
        path = self._path_for(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not req.overwrite:
            raise BlobConflict("blob exists and overwrite=False")

        sha256_hex = None
        size = 0

        def write_sync():
            nonlocal sha256_hex, size
            h = hashlib.sha256() if req.compute_sha256 else None
            with open(path, "wb") as f:
                if req.data is not None:
                    f.write(req.data)
                    size_ = len(req.data)
                    size += size_
                    if h: h.update(req.data)
                elif req.chunks is not None:
                    for chunk in req.chunks:  # Iterable[bytes]
                        f.write(chunk)
                        size_ = len(chunk)
                        size += size_
                        if h: h.update(chunk)
                else:
                    raise BlobValidation("either data or chunks must be provided")
            if h:
                sha256_hex = h.hexdigest()

        await asyncio.to_thread(write_sync)

        meta = BlobMeta(size=size, content_type=req.content_type, sha256=sha256_hex)
        return PutBlobResult(ref=ref, meta=meta)

    async def get_blob_stream(self, req: GetBlobRequest) -> AsyncIterator[bytes]:
        path = self._path_for(req.ref)
        if not path.exists():
            raise BlobNotFound("blob not found")

        start = req.range_start or 0
        end = req.range_end

        def reader():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = None if end is None else (end - start + 1)
                chunk_size = 64 * 1024
                while True:
                    if remaining is not None and remaining <= 0:
                        break
                    to_read = chunk_size if remaining is None else min(chunk_size, remaining)
                    data = f.read(to_read)
                    if not data:
                        break
                    if remaining is not None:
                        remaining -= len(data)
                    yield data

        for chunk in await asyncio.to_thread(lambda: list(reader())):
            yield chunk

    async def head_blob(self, ref) -> HeadBlobResult:
        path = self._path_for(ref)
        if not path.exists():
            raise BlobNotFound("blob not found")

        def stat_sync():
            st = os.stat(path)
            return st.st_size

        size = await asyncio.to_thread(stat_sync)
        return HeadBlobResult(ref=ref, meta=BlobMeta(size=size))

    async def delete_blob(self, req: DeleteBlobRequest) -> DeleteBlobResult:
        path = self._path_for(req.ref)
        if not path.exists():
            if req.missing_ok:
                return DeleteBlobResult(ref=req.ref, deleted=False)
            raise BlobNotFound("blob not found")

        def rm():
            os.remove(path)

        await asyncio.to_thread(rm)
        return DeleteBlobResult(ref=req.ref, deleted=True)

    async def list_blobs(self, req: ListBlobsRequest) -> ListBlobsResult:
        base = _safe_join(self.root, req.tenant_id, req.bucket)
        if not base.exists():
            return ListBlobsResult(tenant_id=req.tenant_id, bucket=req.bucket, items=[], next_cursor=None)

        prefix = req.prefix.strip("/\\")
        items = []
        count = 0
        start_after = req.cursor

        def iter_files():
            for dirpath, _, filenames in os.walk(base):
                for fn in filenames:
                    full = Path(dirpath) / fn
                    rel = str(full.relative_to(base)).replace("\\", "/")
                    if prefix and not rel.startswith(prefix):
                        continue
                    yield rel, full

        seen_start = start_after is None
        for rel, full in iter_files():
            if not seen_start:
                if rel == start_after:
                    seen_start = True
                continue
            size = os.path.getsize(full)
            items.append(BlobItem(key=rel, meta=BlobMeta(size=size)))
            count += 1
            if count >= req.limit:
                next_cursor = rel
                return ListBlobsResult(
                    tenant_id=req.tenant_id, bucket=req.bucket, items=items, next_cursor=next_cursor
                )

        return ListBlobsResult(tenant_id=req.tenant_id, bucket=req.bucket, items=items, next_cursor=None)

    async def create_presigned_url(self, req: PresignRequest) -> Optional[PresignResult]:
        # Local FS does not support presigned URLs; return None
        return None

### 7) S3 Adapter
