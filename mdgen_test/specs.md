Awesome — here’s the first full iteration of the **RateLimiter** component (spec ➜ contracts ➜ implementation ➜ middleware ➜ API router ➜ tests). It follows the same contract-driven style we’ve been using, with testability + observability baked in. I added a TODO list in the spec for next passes.

---

```python
# 66696c657374617274 ./components/ratelimiter/spec.md
# RateLimiter — Contract-Driven Spec (v0.1)
#
# Project: lbp3-rs (FastAPI remote server for a RAG chat app)
# Priorities: Testability + Observability + Swap-able internals (ports/adapters)
# Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide request throttling/quotas for API consumers (per-IP, per-user, per-tenant, global) using configurable policies. Designed to be used:
- (a) as an ASGI middleware in our FastAPI apps, and/or
- (b) as a small service/router exposing explicit “check/consume/reset” edges for other services.

## 2) Responsibilities
- Enforce rate limits via standard algorithms:
  - Token Bucket (default): bursty traffic with sustained rate.
  - Leaky Bucket (optional path): steady drain, queue semantics (first version: simple reject on overflow).
- Policy targeting & keying strategies:
  - key scopes: ip | user | tenant | global | custom
  - matchers by method + path (regex) with priority/first-match semantics.
- Return standard rate-limit headers:
  - `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` (on 429).
- Safe to run in single-process (in-memory store) and multi-process (future Redis adapter).
- Telemetry: OTel spans/attributes for decisions (allow/deny), counters/timers for cost, wait, retries.
- Testability: deterministic time via injected time provider; in-memory store for unit tests.

## 3) Edges (HTTP/ASGI)
### 3.1 ASGI Middleware (primary usage)
- Applies configured policies to incoming requests.
- Builds a limit key based on configured scope:
  - ip: `client.host`
  - user: `X-User-Id` header (placeholder until AuthService integration)
  - tenant: `X-Tenant-Id` header
  - global: constant
  - custom: optional callable hook
- On allow: attach headers (limit/remaining/reset).
- On deny: return 429 JSON `{ "error": "rate_limited", "retry_after": <seconds> }` with headers.

### 3.2 Router (service surface)
- `POST /ratelimiter/consume` — body: { key, policy, cost? } → { allowed, remaining, retry_after? }
- `GET  /ratelimiter/quota/{key}` — inspect current counters for debugging/ops
- `POST /ratelimiter/reset` — body: { key } → reset state (ops convenience)

> Note: Router is optional; middleware is the standard integration in other components like ApiGateway.

## 4) Contracts (Ports/DTOs)
- `Policy`:
  - `name: str`
  - `algorithm: Literal["token_bucket","leaky_bucket"]` (default token)
  - `rate: int` (tokens per period)
  - `period: int` (seconds for the rate window)
  - `burst: int` (max tokens in bucket)
  - `scope: Literal["ip","user","tenant","global","custom"]`
  - `path_pattern: str` (regex)
  - `methods: list[str] | None` (if None, all)
  - `cost: int = 1` (default cost per request)
  - `metadata: dict[str, Any] = {}` (future: plan tier, notes)
- `ConsumeRequest` / `ConsumeResult` (for the router)
- Port: `StateStore` with minimal atomic ops for concurrency (in-mem impl now, Redis later)
  - get(key) → value
  - set(key, value)
  - update(key, fn) → atomic compute-and-set (lock-guarded in memory; script in Redis later)

## 5) Internals
- Token Bucket state per key: `{ tokens: float, last_refill_ts: float }`
- Refill on each consume: 
```

new\_tokens = min(burst, tokens + elapsed \* (rate / period))
if new\_tokens >= cost: allow; tokens = new\_tokens - cost
else: deny; compute retry\_after = ceil((cost - new\_tokens) / (rate / period))

```
- Leaky Bucket (first pass): track `level` and drain at `rate/period`, reject if `level + cost > burst`.

## 6) Storage
- v0: `InMemoryStore` with lock, good for unit tests and single-process dev.
- vNext: `RedisStore` using Lua for atomic update; config via env.

## 7) Configuration
- Middleware accepts a list of `Policy` entries ordered by priority.
- First matching policy applies (method/path).
- Skip list for health endpoints (e.g., `/healthz`).
- Header names for user/tenant configurable (defaults: `X-User-Id`, `X-Tenant-Id`).

## 8) Security & Multi-Tenancy
- Key scopes rely on upstream AuthService to populate headers/JWT. For now, headers stub.
- Tenants should never impact each other’s quotas: tenant scope must incorporate tenant id into key.
- Validate inputs to prevent pathologically large costs/periods.

## 9) Observability
- OTel span `ratelimiter.consume`: attributes
- `decision.allow` bool
- `policy.name`, `scope`, `key`, `cost`, `remaining`, `retry_after`
- Structured logs at INFO for denies (to help ops), DEBUG for allows.
- Metrics (vNext): counters for allows/denies per policy.

## 10) Errors
- 429 with `error=rate_limited` when deny.
- 400 for invalid policy values via Pydantic validation.

## 11) TODO (next iterations)
- [ ] Redis adapter with Lua script for atomic bucket update.
- [ ] Integration with AuthService JWT (extract user/tenant from token).
- [ ] Config/registry source in `components.toml` (policy sets by plan tier).
- [ ] Per-route overrides via FastAPI dependency wrapper.
- [ ] Export Prometheus metrics.
- [ ] Golden fixtures for decision logs.
```

---

```python
# 66696c657374617274 ./components/ratelimiter/contracts.py
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, PositiveInt, field_validator
import re

Algorithm = Literal["token_bucket", "leaky_bucket"]
Scope = Literal["ip", "user", "tenant", "global", "custom"]

class Policy(BaseModel):
    name: str = Field(..., description="Unique policy name")
    algorithm: Algorithm = Field("token_bucket")
    rate: PositiveInt = Field(..., description="Tokens per period")
    period: PositiveInt = Field(..., description="Period length in seconds")
    burst: PositiveInt = Field(..., description="Max tokens in bucket")
    scope: Scope = Field("ip")
    path_pattern: str = Field(r".*", description="Regex to match request path")
    methods: Optional[List[str]] = Field(None, description="List of HTTP methods; None means all")
    cost: PositiveInt = Field(1, description="Default cost per request")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("methods")
    @classmethod
    def normalize_methods(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return [m.upper() for m in v]

    def matches(self, method: str, path: str) -> bool:
        if self.methods and method.upper() not in self.methods:
            return False
        return re.search(self.path_pattern, path) is not None


class ConsumeRequest(BaseModel):
    key: str
    policy: Policy
    cost: PositiveInt = 1


class ConsumeResult(BaseModel):
    allowed: bool
    remaining: float
    retry_after: Optional[float] = None
    policy: str
    key: str


class QuotaSnapshot(BaseModel):
    key: str
    tokens: Optional[float] = None
    last_refill_ts: Optional[float] = None
    level: Optional[float] = None
    algorithm: Algorithm
```

---

```python
# 66696c657374617274 ./components/ratelimiter/errors.py
class RateLimitError(Exception):
    """Base error for RateLimiter component."""

class InvalidScopeError(RateLimitError):
    """Raised when an unsupported scope key is requested."""

class NoMatchingPolicyError(RateLimitError):
    """Raised when no policy matches a request and default handling is disabled."""
```

---

```python
# 66696c657374617274 ./components/ratelimiter/store.py
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

class StateStore:
    """Port interface for a key-value atomic update store."""

    def get(self, key: str) -> Optional[dict]:
        raise NotImplementedError

    def set(self, key: str, value: dict) -> None:
        raise NotImplementedError

    def update(self, key: str, fn: Callable[[Optional[dict]], dict]) -> dict:
        """Atomically read-modify-write the value for key and return the new value."""
        raise NotImplementedError


class InMemoryStore(StateStore):
    """Thread-safe in-memory store with coarse-grained lock.

    For single-process dev/testing. Multi-process needs a Redis adapter (vNext).
    """

    def __init__(self):
        self._data: Dict[str, dict] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, key: str, fn):
        with self._lock:
            current = self._data.get(key)
            new_value = fn(current)
            self._data[key] = new_value
            return new_value
```

---

```python
# 66696c657374617274 ./components/ratelimiter/service.py
from __future__ import annotations

import math
import time
from typing import Callable, List, Optional, Tuple

from pydantic import BaseModel
from .contracts import Policy, ConsumeRequest, ConsumeResult, QuotaSnapshot
from .store import StateStore, InMemoryStore

TimeFn = Callable[[], float]

class RateLimiterService:
    """Core limiter implementing token-bucket and leaky-bucket with an abstract state store."""

    def __init__(self, store: Optional[StateStore] = None, now: Optional[TimeFn] = None):
        self.store = store or InMemoryStore()
        self._now = now or time.monotonic

    # ---------- Public API ----------
    def consume(self, key: str, policy: Policy, cost: int = 1) -> ConsumeResult:
        if policy.algorithm == "token_bucket":
            allowed, remaining, retry_after = self._consume_token_bucket(key, policy, cost)
        elif policy.algorithm == "leaky_bucket":
            allowed, remaining, retry_after = self._consume_leaky_bucket(key, policy, cost)
        else:
            raise ValueError(f"Unsupported algorithm: {policy.algorithm}")

        return ConsumeResult(
            allowed=allowed,
            remaining=remaining,
            retry_after=retry_after,
            policy=policy.name,
            key=key,
        )

    def snapshot(self, key: str, policy: Policy) -> QuotaSnapshot:
        state = self.store.get(self._bucket_key(key, policy))
        if policy.algorithm == "token_bucket":
            tokens = None
            last_refill_ts = None
            if state:
                tokens = state.get("tokens")
                last_refill_ts = state.get("last_refill_ts")
            return QuotaSnapshot(
                key=key, tokens=tokens, last_refill_ts=last_refill_ts, algorithm="token_bucket"
            )
        else:
            level = None
            last_refill_ts = None
            if state:
                level = state.get("level")
                last_refill_ts = state.get("last_refill_ts")
            return QuotaSnapshot(
                key=key, level=level, last_refill_ts=last_refill_ts, algorithm="leaky_bucket"
            )

    def reset(self, key: str, policy: Policy) -> None:
        self.store.set(self._bucket_key(key, policy), {})

    # ---------- Internals ----------
    def _bucket_key(self, key: str, policy: Policy) -> str:
        return f"ratelimiter:{policy.algorithm}:{policy.name}:{key}"

    def _consume_token_bucket(self, key: str, policy: Policy, cost: int) -> tuple[bool, float, Optional[float]]:
        bucket_key = self._bucket_key(key, policy)
        now = self._now()

        def update(state):
            if not state:
                state = {"tokens": float(policy.burst), "last_refill_ts": now}
            tokens = state["tokens"]
            last = state["last_refill_ts"]

            rate_per_sec = policy.rate / policy.period
            # refill
            elapsed = max(0.0, now - last)
            tokens = min(float(policy.burst), tokens + elapsed * rate_per_sec)

            allowed = tokens >= cost
            retry_after = None
            if allowed:
                tokens -= cost
            else:
                deficit = cost - tokens
                # time until enough tokens accumulate
                retry_after = math.ceil(deficit / rate_per_sec)

            # update state
            new_state = {"tokens": tokens, "last_refill_ts": now}
            return new_state, allowed, tokens, retry_after

        def wrapper(curr):
            new_state, allowed, rem, retry_after = update(curr)
            return new_state

        # Two passes: first to compute; second store returns new state— but we need decision.
        # Use update once and recompute decision from returned state + inputs.
        decision: dict = {}
        def upd(curr):
            if not curr:
                curr = {"tokens": float(policy.burst), "last_refill_ts": now}
            tokens = curr["tokens"]
            last = curr["last_refill_ts"]
            rate_per_sec = policy.rate / policy.period
            elapsed = max(0.0, now - last)
            tokens = min(float(policy.burst), tokens + elapsed * rate_per_sec)
            allowed = tokens >= cost
            retry_after = None
            if allowed:
                tokens -= cost
            else:
                deficit = cost - tokens
                retry_after = math.ceil(deficit / rate_per_sec)
            new_state = {"tokens": tokens, "last_refill_ts": now}
            decision.update({"allowed": allowed, "remaining": tokens, "retry_after": retry_after})
            return new_state

        self.store.update(bucket_key, upd)
        return decision["allowed"], decision["remaining"], decision["retry_after"]

    def _consume_leaky_bucket(self, key: str, policy: Policy, cost: int) -> tuple[bool, float, Optional[float]]:
        bucket_key = self._bucket_key(key, policy)
        now = self._now()

        def upd(curr):
            if not curr:
                curr = {"level": 0.0, "last_refill_ts": now}
            level = curr["level"]
            last = curr["last_refill_ts"]
            drain_per_sec = policy.rate / policy.period
            elapsed = max(0.0, now - last)
            # drain
            level = max(0.0, level - elapsed * drain_per_sec)

            allowed = (level + cost) <= float(policy.burst)
            retry_after = None
            if allowed:
                level += cost
            else:
                # Time until the bucket drains enough for 'cost'
                needed = (level + cost) - float(policy.burst)
                # To make room for 'needed', but more simply: time until (level) falls to (burst - cost)
                target_level = float(policy.burst) - cost
                if level <= target_level:
                    retry_after = 0
                else:
                    retry_after = math.ceil((level - target_level) / drain_per_sec)

            new_state = {"level": level, "last_refill_ts": now}
            decision.update({"allowed": allowed, "remaining": max(0.0, float(policy.burst) - level), "retry_after": retry_after})
            return new_state

        decision: dict = {}
        self.store.update(bucket_key, upd)
        return decision["allowed"], decision["remaining"], decision["retry_after"]
```

---

```python
# 66696c657374617274 ./components/ratelimiter/middleware.py
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
```

---

```python
# 66696c657374617274 ./components/ratelimiter/app.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from .contracts import ConsumeRequest, ConsumeResult, Policy, QuotaSnapshot
from .service import RateLimiterService

router = APIRouter(prefix="/ratelimiter", tags=["ratelimiter"])

def get_service():
    # Dependency hook for DI; can be overridden in tests / app factory
    return RateLimiterService()

@router.post("/consume", response_model=ConsumeResult)
def consume(req: ConsumeRequest, svc: RateLimiterService = Depends(get_service)):
    return svc.consume(key=req.key, policy=req.policy, cost=req.cost)

@router.get("/quota/{key}", response_model=QuotaSnapshot)
def quota(key: str, algorithm: str, name: str, svc: RateLimiterService = Depends(get_service)):
    # reconstruct a minimal policy for lookup semantics
    if algorithm not in ("token_bucket", "leaky_bucket"):
        raise HTTPException(status_code=400, detail="invalid algorithm")
    # arbitrary defaults; used only to locate state shape
    dummy = Policy(
        name=name,
        algorithm=algorithm, rate=1, period=1, burst=1,
        scope="global", path_pattern=".*"
    )
    return svc.snapshot(key, dummy)

class ResetRequest(BaseModel):
    key: str
    policy: Policy

@router.post("/reset")
def reset(req: ResetRequest, svc: RateLimiterService = Depends(get_service)):
    svc.reset(req.key, req.policy)
    return {"ok": True}
```

---

```python
# 66696c657374617274 ./components/ratelimiter/__init__.py
from .contracts import Policy, ConsumeRequest, ConsumeResult, QuotaSnapshot
from .service import RateLimiterService
from .middleware import RateLimiterMiddleware

__all__ = [
    "Policy",
    "ConsumeRequest",
    "ConsumeResult",
    "QuotaSnapshot",
    "RateLimiterService",
    "RateLimiterMiddleware",
]
```

---

```python
# 66696c657374617274 ./tests/test_ratelimiter_service.py
import math
import pytest

from components.ratelimiter.contracts import Policy
from components.ratelimiter.service import RateLimiterService
from components.ratelimiter.store import InMemoryStore

def make_clock(start=0.0):
    t = {"now": float(start)}
    def now():
        return t["now"]
    def advance(dt):
        t["now"] += float(dt)
    return now, advance

def test_token_bucket_basic_allow_and_deny():
    store = InMemoryStore()
    now, advance = make_clock(0.0)
    svc = RateLimiterService(store=store, now=now)
    policy = Policy(
        name="p1", algorithm="token_bucket",
        rate=2, period=1, burst=2,
        scope="global", path_pattern=r".*"
    )

    # bucket starts full (2 tokens)
    r1 = svc.consume("global:*", policy, cost=1)
    assert r1.allowed and math.isclose(r1.remaining, 1.0, rel_tol=1e-6)

    r2 = svc.consume("global:*", policy, cost=1)
    assert r2.allowed and math.isclose(r2.remaining, 0.0, rel_tol=1e-6)

    r3 = svc.consume("global:*", policy, cost=1)
    assert not r3.allowed
    assert r3.retry_after == 1  # need ~0.5s for 1 token at 2/s → ceil → 1

    # advance 0.5s → should still ceil to 1 if we recheck immediately
    advance(0.5)
    r4 = svc.consume("global:*", policy, cost=1)
    assert not r4.allowed
    assert r4.retry_after == 1

    # advance another 0.5s → total 1.0s elapsed → 2 tokens regained
    advance(0.5)
    r5 = svc.consume("global:*", policy, cost=1)
    assert r5.allowed
    assert r5.remaining >= 0.0

def test_leaky_bucket_deny_then_allow_after_drain():
    store = InMemoryStore()
    now, advance = make_clock(0.0)
    svc = RateLimiterService(store=store, now=now)
    policy = Policy(
        name="p2", algorithm="leaky_bucket",
        rate=2, period=1, burst=2,
        scope="global", path_pattern=r".*"
    )

    # First two allowed (burst 2)
    assert svc.consume("k", policy, 1).allowed
    assert svc.consume("k", policy, 1).allowed

    # Third should deny
    r3 = svc.consume("k", policy, 1)
    assert not r3.allowed
    assert r3.retry_after >= 0

    # Advance time to drain enough for 1
    advance(1.0)  # drains 2 tokens per second → level should drop to 0
    r4 = svc.consume("k", policy, 1)
    assert r4.allowed
```

---

```python
# 66696c657374617274 ./tests/test_ratelimiter_middleware.py
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from components.ratelimiter.contracts import Policy
from components.ratelimiter.middleware import RateLimiterMiddleware
from components.ratelimiter.service import RateLimiterService
from components.ratelimiter.store import InMemoryStore

@pytest.mark.anyio
async def test_middleware_basic_flow():
    app = FastAPI()

    policy = Policy(
        name="per_ip",
        algorithm="token_bucket",
        rate=2,
        period=1,
        burst=2,
        scope="ip",
        path_pattern=r"^/echo$",
        methods=["GET"],
    )

    # Deterministic clock for service used by middleware
    t = {"now": 0.0}
    def now():
        return t["now"]
    store = InMemoryStore()
    svc = RateLimiterService(store=store, now=now)

    app.add_middleware(
        RateLimiterMiddleware,
        policies=[policy],
        service=svc,
        skip_paths=[r"^/healthz$"],
    )

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/echo")
    async def echo():
        return {"ok": True}

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # healthz should bypass
        r = await ac.get("/healthz")
        assert r.status_code == 200

        # allow 2, then deny
        r1 = await ac.get("/echo")
        assert r1.status_code == 200
        assert "X-RateLimit-Limit" in r1.headers
        r2 = await ac.get("/echo")
        assert r2.status_code == 200
        r3 = await ac.get("/echo")
        assert r3.status_code == 429
        assert r3.json()["error"] == "rate_limited"
        assert "Retry-After" in r3.headers

        # advance time → allow again
        t["now"] += 1.0
        r4 = await ac.get("/echo")
        assert r4.status_code == 200
```

---

### How to integrate

* **As middleware in ApiGateway / any FastAPI service:**

  ```python
  # 66696c657374617274 ./components/apigateway/wiring_example_ratelimiter.py
  from fastapi import FastAPI
  from components.ratelimiter import Policy, RateLimiterMiddleware

  app = FastAPI()

  policies = [
      Policy(
          name="tenant_plan_basic",
          algorithm="token_bucket",
          rate=60, period=60, burst=60,
          scope="tenant",
          path_pattern=r"^/v1/.*",
          methods=None,
          cost=1,
      )
  ]

  app.add_middleware(RateLimiterMiddleware, policies=policies)
  ```

* **As a router (optional) mounted into a service:**

  ```python
  # 66696c657374617274 ./components/ratelimiter/router_mount_example.py
  from fastapi import FastAPI
  from components.ratelimiter.app import router as ratelimiter_router

  app = FastAPI()
  app.include_router(ratelimiter_router)
  ```

If you want, I can also add a small **RedisStore** skeleton in the next pass (kept TODO now).
