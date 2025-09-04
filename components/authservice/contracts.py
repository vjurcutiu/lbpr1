from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple
from pydantic import BaseModel, Field, constr, conlist

# ---------- Unified Wire Format (UWF) ----------
class ErrorPayload(BaseModel):
    type: Literal["AUTH_ERROR","RATE_LIMIT","VALIDATION","NOT_FOUND","CONFLICT","UPSTREAM","INTERNAL"]
    code: constr(strip_whitespace=True, min_length=1)
    message: constr(strip_whitespace=True, min_length=1)
    details: Optional[Dict[str, Any]] = None

class MetaPayload(BaseModel):
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    tenant_id: Optional[str] = None
    duration_ms: Optional[int] = None

class UWFResponse(BaseModel):
    ok: bool
    result: Optional[Any] = None
    error: Optional[ErrorPayload] = None
    meta: MetaPayload = Field(default_factory=MetaPayload)

# ---------- Domain Models ----------
class User(BaseModel):
    id: str
    email: constr(strip_whitespace=True, min_length=3)
    display_name: Optional[str] = None
    tenant_id: str
    is_active: bool = True
    scopes: List[str] = Field(default_factory=list)

class AccessTokenClaims(BaseModel):
    sub: str
    tenant_id: str
    scopes: List[str]
    iat: int
    exp: int
    iss: Optional[str] = None
    aud: Optional[str] = None
    jti: Optional[str] = None

class RefreshTokenClaims(BaseModel):
    sub: str
    tenant_id: str
    typ: Literal["refresh"] = "refresh"
    iat: int
    exp: int
    iss: Optional[str] = None
    aud: Optional[str] = None
    jti: Optional[str] = None

class IssuedTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int

# ---------- Ports (Contracts) ----------
class TokenSignerPort(Protocol):
    """
    Contract for JWT signing/verification and key rotation metadata.
    Implementation can be HS256/RS256/etc.
    """
    def sign(self, claims: Dict[str, Any], *, headers: Optional[Dict[str, Any]] = None) -> str: ...
    def verify(self, token: str) -> Dict[str, Any]: ...
    def active_kid(self) -> Optional[str]: ...
    def list_kids(self) -> List[str]: ...

class UserRepoPort(Protocol):
    """
    Contract for user lookup & credential validation.
    """
    def get_user_by_credentials(self, *, email: str, password: str) -> Optional[User]: ...
    def get_user_by_id(self, user_id: str) -> Optional[User]: ...

class ClockPort(Protocol):
    def now_utc_ts(self) -> int: ...

# ---------- Service I/O ----------
class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class MeResponse(BaseModel):
    user: User

# ---------- Errors ----------
class AuthErrorCodes:
    BAD_CREDENTIALS = "BAD_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"
    INVALID_TOKEN = "INVALID_TOKEN"
    MISSING_SCOPE = "MISSING_SCOPE"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    CONFIG_ERROR = "CONFIG_ERROR"