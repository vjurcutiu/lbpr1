from __future__ import annotations


class VectorStoreError(RuntimeError):
    """Base typed error for all vector store failures."""


class BadRequest(VectorStoreError):
    """Invalid arguments or contract violation."""


class BackendUnavailable(VectorStoreError):
    """Adapter backend unavailable or misconfigured."""


class NamespaceNotFound(VectorStoreError):
    """Referred namespace does not exist (adapter-dependent semantics)."""


class ConflictError(VectorStoreError):
    """Conflicting operation (e.g., duplicate ids on constrained backends)."""

---


