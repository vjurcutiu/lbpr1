from __future__ import annotations


class IndexerError(Exception):
    """Base error for Indexer component."""


class ValidationError(IndexerError):
    """Raised when payload validation or preconditions fail."""


class NotFoundError(IndexerError):
    """Raised when a requested job is not found."""


class VectorStoreError(IndexerError):
    """Raised when vector store operations fail."""


