"""
Indexer component package.
Exports FastAPI router via get_router() and the IndexerService for DI.
"""
from .routes import get_router
from .service import IndexerService
from .adapters_inmemory import InMemoryJobStore, InMemoryVectorStore, SimpleChunker, DummyEmbedder

__all__ = [
    "get_router",
    "IndexerService",
    "InMemoryJobStore",
    "InMemoryVectorStore",
    "SimpleChunker",
    "DummyEmbedder",
]
````


