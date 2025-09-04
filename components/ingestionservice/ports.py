from __future__ import annotations

from typing import Any, Dict, List, Optional


class BlobStorageAdapterPort:
    def put_bytes(
        self,
        tenant_id: str,
        path_hint: str,
        raw: bytes,
        content_type: str,
    ) -> str:
        """
        Store bytes and return a stable blob_uri (e.g., 'blob://tenant/bucket/path').
        Must be idempotent for identical content/path_hint if feasible.
        """
        raise NotImplementedError


class MetadataServicePort:
    def upsert_file(
        self,
        tenant_id: str,
        blob_uri: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register/Upsert file metadata. Returns metadata_id (stable).
        """
        raise NotImplementedError


class IndexerPort:
    def create_job(
        self,
        tenant_id: str,
        items: List[Dict[str, Any]],
    ) -> str:
        """
        Create an indexing job referencing the ingested items (blob_uris + metadata).
        Returns index_job_id.
        """
        raise NotImplementedError


class AuthContextPort:
    """
    Very thin shim to extract tenant_id/user_id from the request context.
    For tests we may inject directly.
    """

    def get_tenant_id(self) -> str:
        raise NotImplementedError

    def get_user_id(self) -> str:
        raise NotImplementedError


