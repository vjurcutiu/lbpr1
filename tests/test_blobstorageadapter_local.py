import asyncio
import tempfile
from pathlib import Path
import pytest

from components.blobstorageadapter.adapters.local_fs import LocalFSBlobAdapter
from components.blobstorageadapter.contracts import (
    BlobRef, PutBlobRequest, GetBlobRequest, DeleteBlobRequest, ListBlobsRequest
)
from components.blobstorageadapter.errors import BlobNotFound

@pytest.mark.asyncio
async def test_put_head_get_list_delete_localfs():
    with tempfile.TemporaryDirectory() as tmp:
        adapter = LocalFSBlobAdapter(tmp)

        ref = BlobRef(tenant_id="t1", bucket="ingest", key="folder/hello.bin")
        data = b"hello world" * 100

        # put
        put_res = await adapter.put_blob(PutBlobRequest(ref=ref, data=data, content_type="application/octet-stream", compute_sha256=True))
        assert put_res.meta.size == len(data)
        assert put_res.meta.sha256 is not None

        # head
        head_res = await adapter.head_blob(ref)
        assert head_res.meta.size == len(data)

        # get
        got = b""
        async for chunk in adapter.get_blob_stream(GetBlobRequest(ref=ref)):
            got += chunk
        assert got == data

        # list
        list_res = await adapter.list_blobs(ListBlobsRequest(tenant_id="t1", bucket="ingest", prefix="folder"))
        assert any(item.key == "folder/hello.bin" for item in list_res.items)

        # delete
        del_res = await adapter.delete_blob(DeleteBlobRequest(ref=ref, missing_ok=False))
        assert del_res.deleted is True

        # get after delete -> not found
        with pytest.raises(BlobNotFound):
            async for _ in adapter.get_blob_stream(GetBlobRequest(ref=ref)):
                pass
