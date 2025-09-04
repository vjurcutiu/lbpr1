from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from .contracts import ConsumeRequest, ConsumeResult, Policy, QuotaSnapshot
from .service import RateLimiterService

router = APIRouter(prefix="/ratelimiter", tags=["ratelimiter"])

def get_service():
    # Dependency hook for DI; can be overridden in tests / app factory
    return RateLimiterService()

@router.post("/consume", response_model=ConsumeResult)
def consume(req: ConsumeRequest, svc: RateLimiterService = Depends(get_service)):
    return svc.consume(key=req.key, policy=req.policy, cost=req.cost)

@router.get("/quota/{key}", response_model=QuotaSnapshot)
def quota(key: str, algorithm: str, name: str, svc: RateLimiterService = Depends(get_service)):
    # reconstruct a minimal policy for lookup semantics
    if algorithm not in ("token_bucket", "leaky_bucket"):
        raise HTTPException(status_code=400, detail="invalid algorithm")
    # arbitrary defaults; used only to locate state shape
    dummy = Policy(
        name=name,
        algorithm=algorithm, rate=1, period=1, burst=1,
        scope="global", path_pattern=".*"
    )
    return svc.snapshot(key, dummy)

class ResetRequest(BaseModel):
    key: str
    policy: Policy

@router.post("/reset")
def reset(req: ResetRequest, svc: RateLimiterService = Depends(get_service)):
    svc.reset(req.key, req.policy)
    return {"ok": True}