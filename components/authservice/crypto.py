from __future__ import annotations
import base64, json, hmac, hashlib, time, uuid
from typing import Any, Dict, List, Optional
from .contracts import TokenSignerPort

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def _unb64url(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

class HS256TokenSigner(TokenSignerPort):
    """
    Minimal HS256 JWT signer for zero-deps portability in early iterations.
    Supports kid in header for future key rotation.
    WARNING: For prod, prefer a battle-tested lib; keep this as a thin adapter.
    """
    def __init__(self, secret: str, kid: Optional[str] = "primary"):
        if not secret:
            raise ValueError("HS256TokenSigner requires non-empty secret")
        self._secret = secret.encode("utf-8")
        self._kid = kid

    def sign(self, claims: Dict[str, Any], *, headers: Optional[Dict[str, Any]] = None) -> str:
        base_headers = {"alg": "HS256", "typ": "JWT"}
        if self._kid:
            base_headers["kid"] = self._kid
        if headers:
            base_headers.update(headers)
        header_b64 = _b64url(json.dumps(base_headers, separators=(",",":")).encode("utf-8"))
        payload_b64 = _b64url(json.dumps(claims, separators=(",",":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{payload_b64}.{_b64url(sig)}"

    def verify(self, token: str) -> Dict[str, Any]:
        try:
            header_b64, payload_b64, sig_b64 = token.split(".")
        except ValueError:
            raise ValueError("Invalid token format")
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _unb64url(sig_b64)):
            raise ValueError("Signature mismatch")
        payload = json.loads(_unb64url(payload_b64).decode("utf-8"))
        now = int(time.time())
        if "exp" in payload and now >= int(payload["exp"]):
            raise ValueError("Token expired")
        return payload

    def active_kid(self) -> Optional[str]:
        return self._kid

    def list_kids(self) -> List[str]:
        return [self._kid] if self._kid else []