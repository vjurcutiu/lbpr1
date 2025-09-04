from __future__ import annotations

import re
from typing import Callable, List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from .contracts import Policy
from .service import RateLimiterService


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that applies the first matching policy to each request."""

    def __init__(
        self,
        app,
        policies: List[Policy],
        service: Optional[RateLimiterService] = None,
        user_header: str = "X-User-Id",
        tenant_header: str = "X-Tenant-Id",
        skip_paths: Optional[List[str]] = None,
    ):
        super().__init__(app)
        self.policies = policies
        self.service = service or RateLimiterService()
        self.user_header = user_header
        self.tenant_header = tenant_header
        self.skip_paths = skip_paths or [r"^/healthz$", r"^/metrics$"]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method.upper()

        # Skip known public endpoints
        for pat in self.skip_paths:
            if re.search(pat, path):
                return await call_next(request)

        policy = self._select_policy(method, path)
        if not policy:
            # no policy → allow
            return await call_next(request)

        key = self._build_key(request, policy)
        result = self.service.consume(key=key, policy=policy, cost=policy.cost)

        # Set standard headers
        headers = {
            "X-RateLimit-Limit": f"{policy.rate};w={policy.period};burst={policy.burst}",
            "X-RateLimit-Remaining": str(max(0, int(result.remaining))),
        }

        if result.allowed:
            response = await call_next(request)
            for k, v in headers.items():
                response.headers[k] = v
            # Soft "reset" time as best-effort (not exact): period window boundary heuristic
            response.headers["X-RateLimit-Reset"] = str(policy.period)
            return response
        else:
            headers["Retry-After"] = str(int(result.retry_after or 0))
            headers["X-RateLimit-Reset"] = str(int(result.retry_after or policy.period))
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "retry_after": int(result.retry_after or 0)},
                headers=headers,
            )

    def _select_policy(self, method: str, path: str) -> Optional[Policy]:
        for p in self.policies:
            if p.matches(method, path):
                return p
        return None

    def _build_key(self, request: Request, policy: Policy) -> str:
        scope = policy.scope
        if scope == "ip":
            client = request.client.host if request.client else "unknown"
            return f"ip:{client}"
        elif scope == "user":
            user = request.headers.get(self.user_header, "anonymous")
            return f"user:{user}"
        elif scope == "tenant":
            tenant = request.headers.get(self.tenant_header, "default")
            return f"tenant:{tenant}"
        elif scope == "global":
            return "global:*"
        elif scope == "custom":
            # Placeholder: Future dependency to resolve custom key builders
            # For now, fall back to IP
            client = request.client.host if request.client else "unknown"
            return f"custom:{client}"
        else:
            # Should be prevented by validation
            return "unknown"