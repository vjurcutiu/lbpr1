# 66696c657374617274 ./components/authservice/__init__.py
from .service import AuthService, get_auth_service  # expose getter for DI
from .crypto import HS256TokenSigner
from .models import PasswordHasher, InMemoryUserRepo
from .config import AuthConfig
from .deps import set_auth_service, require_scopes
from .routes import router as auth_router

__all__ = [
    "AuthService",
    "get_auth_service",
    "HS256TokenSigner",
    "PasswordHasher",
    "InMemoryUserRepo",
    "AuthConfig",
    "set_auth_service",
    "require_scopes",
    "auth_router",
]
