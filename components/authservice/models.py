from __future__ import annotations
import hashlib
from typing import Optional
from pydantic import BaseModel
from .contracts import User

class PasswordHasher:
    """
    Simple PBKDF2 hasher (no external deps).
    In future iterations, wrap passlib/argon2 via a port.
    """
    def __init__(self, iterations: int = 100_000):
        self.iterations = iterations

    def hash(self, password: str, salt: str) -> str:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), self.iterations, dklen=32)
        return f"pbkdf2_sha256${self.iterations}${salt}${dk.hex()}"

    def verify(self, password: str, encoded: str) -> bool:
        try:
            _, iters_s, salt, hex_dk = encoded.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters_s), dklen=32).hex()
            return dk == hex_dk
        except Exception:
            return False

class InMemoryUserRepo:
    """
    Test/dummy repo. Keys by email and id.
    """
    def __init__(self, hasher: PasswordHasher):
        self._users_by_email = {}
        self._users_by_id = {}
        self._hasher = hasher

    def add_user(self, *, id: str, email: str, display_name: str, tenant_id: str, password: str, scopes: list[str], is_active: bool = True):
        salt = f"{tenant_id}:{email}"
        pw_hash = self._hasher.hash(password, salt)
        user = User(id=id, email=email, display_name=display_name, tenant_id=tenant_id, is_active=is_active, scopes=scopes)
        record = {"user": user, "pw": pw_hash, "salt": salt}
        self._users_by_email[email] = record
        self._users_by_id[id] = record

    # Satisfy UserRepoPort
    def get_user_by_credentials(self, *, email: str, password: str) -> Optional[User]:
        rec = self._users_by_email.get(email)
        if not rec:
            return None
        if self._hasher.verify(password, rec["pw"]):
            return rec["user"]
        return None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        rec = self._users_by_id.get(user_id)
        return rec["user"] if rec else None