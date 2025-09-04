from __future__ import annotations
from typing import Optional
from pydantic import BaseModel
from .contracts import ErrorPayload

class AuthServiceException(Exception):
    def __init__(self, payload: ErrorPayload):
        super().__init__(payload.message)
        self.payload = payload

def make_auth_error(code: str, message: str, *, details: Optional[dict] = None) -> AuthServiceException:
    return AuthServiceException(
        ErrorPayload(type="AUTH_ERROR", code=code, message=message, details=details)
    )