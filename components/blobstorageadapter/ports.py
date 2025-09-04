
from __future__ import annotations
from typing import AsyncIterator, Optional
from abc import ABC, abstractmethod

from .contracts import (
    PutBlobRequest, PutBlobResult, GetBlobRequest, GetBlobResult,
    DeleteBlobRequest, DeleteBlobResult, ListBlobsRequest, ListBlobsResult,
    HeadBlobResult, PresignRequest, PresignResult
)

class BlobStoragePort(ABC):
    @abstractmethod
    async def put_blob(self, req: PutBlobRequest) -> PutBlobResult: ...

    @abstractmethod
    async def get_blob_stream(self, req: GetBlobRequest) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def head_blob(self, ref) -> HeadBlobResult: ...

    @abstractmethod
    async def delete_blob(self, req: DeleteBlobRequest) -> DeleteBlobResult: ...

    @abstractmethod
    async def list_blobs(self, req: ListBlobsRequest) -> ListBlobsResult: ...

    @abstractmethod
    async def create_presigned_url(self, req: PresignRequest) -> Optional[PresignResult]: ...

### 4) Errors
