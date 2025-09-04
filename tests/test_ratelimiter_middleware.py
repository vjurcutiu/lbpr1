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