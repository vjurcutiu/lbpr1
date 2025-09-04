from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from .contracts import LoginRequest, RefreshRequest, UWFResponse, MeResponse
from .deps import get_auth_service, require_scopes
from .errors import AuthServiceException

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=UWFResponse)
def login(req: LoginRequest, svc = Depends(get_auth_service)):
    try:
        tokens = svc.login(req)
        return UWFResponse(ok=True, result=tokens)
    except AuthServiceException as ex:
        return UWFResponse(ok=False, error=ex.payload)

@router.post("/refresh", response_model=UWFResponse)
def refresh(req: RefreshRequest, svc = Depends(get_auth_service)):
    try:
        tokens = svc.refresh(req)
        return UWFResponse(ok=True, result=tokens)
    except AuthServiceException as ex:
        return UWFResponse(ok=False, error=ex.payload)

@router.get("/me", response_model=UWFResponse)
def me(current_user = Depends(require_scopes([]))):
    return UWFResponse(ok=True, result=MeResponse(user=current_user))