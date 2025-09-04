
from __future__ import annotations

class BlobError(Exception):
    """Base class for blob adapter errors."""

class BlobNotFound(BlobError):
    pass

class BlobConflict(BlobError):
    pass

class BlobValidation(BlobError):
    pass

class BlobUpstream(BlobError):
    pass

class BlobInternal(BlobError):
    pass

