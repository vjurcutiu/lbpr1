from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .contracts import CreateIngestionRequest, CreateIngestionResponse, IngestionJob
from .errors import BadRequestError
from .ports import AuthContextPort, BlobStorageAdapterPort, IndexerPort, MetadataServicePort
from .repository import InMemoryIngestionRepo
from .service import IngestionService


# ---- Dependency shims (replace with real DI container in app wiring) ----
class _AuthCtx(AuthContextPort):
    def __init__(self, tenant_id: str, user_id: str) -> None:
        self._tenant_id = tenant_id
        self._user_id = user_id

    def get_tenant_id(self) -> str:
        return self._tenant_id

    def get_user_id(self) -> str:
        return self._user_id


def get_auth_ctx(request: Request) -> _AuthCtx:
    # In real app: extract from JWT/middleware. For now, accept headers as a simple stand-in.
    tenant_id = request.headers.get("X-Tenant-Id", "test-tenant")
    user_id = request.headers.get("X-User-Id", "test-user")
    return _AuthCtx(tenant_id=tenant_id, user_id=user_id)


# These would be provided by the application container; here we store singletons per-process.
_repo_singleton = InMemoryIngestionRepo()
_blob_adapter_singleton: BlobStorageAdapterPort
_meta_service_singleton: MetadataServicePort
_indexer_port_singleton: IndexerPort


def set_ports_for_ingestion(
    blob: BlobStorageAdapterPort, meta: MetadataServicePort, indexer: IndexerPort
) -> None:
    global _blob_adapter_singleton, _meta_service_singleton, _indexer_port_singleton
    _blob_adapter_singleton = blob
    _meta_service_singleton = meta
    _indexer_port_singleton = indexer


def get_service(auth: _AuthCtx = Depends(get_auth_ctx)) -> IngestionService:
    return IngestionService(
        tenant_id=auth.get_tenant_id(),
        repo=_repo_singleton,
        blob=_blob_adapter_singleton,
        meta=_meta_service_singleton,
        indexer=_indexer_port_singleton,
    )


# ---- Router ----
router = APIRouter(prefix="/ingestions", tags=["ingestions"])


@router.post("", response_model=CreateIngestionResponse, status_code=status.HTTP_201_CREATED)
def create_ingestion(req: CreateIngestionRequest, svc: IngestionService = Depends(get_service)):
    try:
        job = svc.create_ingestion(req)
    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CreateIngestionResponse(job=job)


@router.get("/{job_id}", response_model=IngestionJob)
def get_ingestion(job_id: str, svc: IngestionService = Depends(get_service)):
    job = svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.get("/{job_id}/events")
def list_events(job_id: str, svc: IngestionService = Depends(get_service)):
    job = svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return {"events": svc.list_events(job_id)}


