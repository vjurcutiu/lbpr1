from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import List
import logging

from .schemas import (
    CreateIndexJobRequest,
    CreateIndexJobResponse,
    JobStatus,
)
from .service import IndexerService
from .adapters_inmemory import InMemoryJobStore, InMemoryVectorStore, SimpleChunker, DummyEmbedder

log = logging.getLogger("indexer.routes")


def _default_service() -> IndexerService:
    # Simple DI for first pass
    return IndexerService(
        chunker=SimpleChunker(),
        embedder=DummyEmbedder(),
        vector_store=InMemoryVectorStore(),
        job_store=InMemoryJobStore(),
    )


def get_router(service_factory=_default_service) -> APIRouter:
    r = APIRouter(prefix="/indexer", tags=["indexer"])
    service = service_factory()

    @r.post("/jobs", response_model=CreateIndexJobResponse, status_code=201)
    def create_job(payload: CreateIndexJobRequest, svc: IndexerService = Depends(lambda: service)):
        job_id = svc.create_job(payload)
        status = svc.get_job(job_id)
        return CreateIndexJobResponse(job_id=job_id, status=status.status)

    @r.get("/jobs/{job_id}", response_model=JobStatus)
    def get_job(job_id: str, svc: IndexerService = Depends(lambda: service)):
        try:
            return svc.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

    @r.get("/jobs/{job_id}/events")
    def list_events(job_id: str, svc: IndexerService = Depends(lambda: service)):
        try:
            return {"job_id": job_id, "events": svc.list_events(job_id)}
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

    @r.get("/health")
    def health():
        return {"ok": True}

    return r


