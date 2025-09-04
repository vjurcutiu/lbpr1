"""
VectorStoreAdapter package export surface.
"""

from .models import (
    VectorRecord,
    DNFFilter,
    FilterCondition,
    QueryMatch,
    UpsertResult,
    QueryResult,
    FetchResult,
    DeleteResult,
    StatsResult,
)
from .errors import (
    VectorStoreError,
    BadRequest,
    BackendUnavailable,
    NamespaceNotFound,
    ConflictError,
)
from .ports import VectorStorePort
````

---


