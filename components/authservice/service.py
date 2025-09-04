from __future__ import annotations
import time, uuid
from typing import Any, Dict, List, Optional
from .contracts import (
    TokenSignerPort, UserRepoPort, ClockPort,
    LoginRequest, RefreshRequest, IssuedTokens,
    AccessTokenClaims, RefreshTokenClaims, User, AuthErrorCodes
)
from .errors import make_auth_error
from .config import AuthConfig

class SystemClock(ClockPort):
    def now_utc_ts(self) -> int:
        return int(time.time())

class AuthService:
    def __init__(
        self,
        *,
        user_repo: UserRepoPort,
        signer: TokenSignerPort,
        cfg: Optional[AuthConfig] = None,
        clock: Optional[ClockPort] = None,
    ):
        self.user_repo = user_repo
        self.signer = signer
        self.cfg = cfg or AuthConfig()
        self.clock = clock or SystemClock()

    # --------- Core operations ----------
    def login(self, req: LoginRequest) -> IssuedTokens:
        user = self.user_repo.get_user_by_credentials(email=req.email, password=req.password)
        if not user:
            raise make_auth_error(AuthErrorCodes.BAD_CREDENTIALS, "Invalid email or password")
        if not user.is_active:
            raise make_auth_error(AuthErrorCodes.INACTIVE_USER, "User inactive")
        return self._issue_for_user(user)

    def refresh(self, req: RefreshRequest) -> IssuedTokens:
        try:
            payload = self.signer.verify(req.refresh_token)
        except Exception as ex:
            raise make_auth_error(AuthErrorCodes.INVALID_TOKEN, f"Invalid refresh token: {ex}")

        if payload.get("typ") != "refresh":
            raise make_auth_error(AuthErrorCodes.INVALID_TOKEN, "Not a refresh token")

        user_id = payload.get("sub")
        user = self.user_repo.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise make_auth_error(AuthErrorCodes.INVALID_TOKEN, "Unknown or inactive user")

        # Optional: enforce tenant match or rotation policy here
        return self._issue_for_user(user)

    def verify_access(self, token: str, *, required_scopes: Optional[List[str]] = None, tenant_id: Optional[str] = None) -> User:
        try:
            payload = self.signer.verify(token)
        except Exception as ex:
            raise make_auth_error(AuthErrorCodes.INVALID_TOKEN, f"Invalid token: {ex}")

        # Basic claims
        sub = payload.get("sub")
        tok_tenant = payload.get("tenant_id")
        scopes = payload.get("scopes", [])
        if tenant_id and tok_tenant != tenant_id:
            raise make_auth_error(AuthErrorCodes.TENANT_MISMATCH, "Tenant mismatch")

        # Scope check (all required must be present)
        if required_scopes:
            missing = [s for s in required_scopes if s not in scopes]
            if missing:
                raise make_auth_error(AuthErrorCodes.MISSING_SCOPE, f"Missing required scopes: {missing}")

        user = self.user_repo.get_user_by_id(sub)
        if not user or not user.is_active:
            raise make_auth_error(AuthErrorCodes.INVALID_TOKEN, "Unknown or inactive user")
        return user

    # --------- Helpers ----------
    def _issue_for_user(self, user: User) -> IssuedTokens:
        now = self.clock.now_utc_ts()
        access_claims = AccessTokenClaims(
            sub=user.id,
            tenant_id=user.tenant_id,
            scopes=user.scopes,
            iat=now,
            exp=now + self.cfg.access_ttl_seconds,
            iss=self.cfg.issuer,
            aud=self.cfg.audience,
            jti=str(uuid.uuid4())
        ).dict()

        refresh_claims = RefreshTokenClaims(
            sub=user.id,
            tenant_id=user.tenant_id,
            iat=now,
            exp=now + self.cfg.refresh_ttl_seconds,
            iss=self.cfg.issuer,
            aud=self.cfg.audience,
            jti=str(uuid.uuid4())
        ).dict()

        access_token = self.signer.sign(access_claims)
        refresh_token = self.signer.sign(refresh_claims, headers={"typ": "JWT"})
        return IssuedTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=self.cfg.access_ttl_seconds
        )