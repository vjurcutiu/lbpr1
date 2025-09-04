# 66696c657374617274 ./components/authservice/deps.py
from typing import Callable, List, Optional

from fastapi import Depends, Header, HTTPException, status

from .service import AuthService, get_auth_service
from .models import User


def get_authorization_header(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> Optional[str]:
    """
    Extract the Authorization header value (e.g., 'Bearer <token>').
    Using Header() ensures we get a plain string during real FastAPI requests.
    """
    return authorization


def require_scopes(required: List[str]) -> Callable[[], Depends]:
    """
    Dependency *factory* that returns a callable. When that callable is invoked,
    it returns a `Depends` object wrapping the real dependency function.
    This supports both idioms:
      - user: User = Depends(require_scopes(["documents:ingest"])())
      - user: User = Depends(require_scopes(["documents:ingest"]))   # also works if you prefer
    """
    def _dep(
        auth: AuthService = Depends(get_auth_service),
        authorization: Optional[str] = Depends(get_authorization_header),
    ) -> User:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header",
            )

        token = authorization.split(" ", 1)[1].strip()
        user = auth.verify_token(token)

        if not auth.has_scopes(user, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {required}",
            )
        return user

    # Return a callable that yields a Depends wrapper when invoked,
    # so tests calling `require_scopes(... )()` don't accidentally call _dep directly.
    def _as_dep() -> Depends:
        return Depends(_dep)

    # Also make the factory itself usable directly by FastAPI (no parenthesis) if needed:
    _as_dep.__fastapi_dependency__ = _dep  # optional hint for tooling
    return _as_dep
