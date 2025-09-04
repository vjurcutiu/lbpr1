from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class AuthConfig:
    alg: str = os.getenv("AUTH_ALG", "HS256")
    secret: str = os.getenv("AUTH_SECRET", "change-me-dev-secret")
    access_ttl_seconds: int = int(os.getenv("ACCESS_TTL_SECONDS", "900"))       # 15 minutes
    refresh_ttl_seconds: int = int(os.getenv("REFRESH_TTL_SECONDS", "1209600")) # 14 days
    issuer: str = os.getenv("AUTH_ISSUER", "lbp3-rs")
    audience: str = os.getenv("AUTH_AUDIENCE", "lbp3-clients")