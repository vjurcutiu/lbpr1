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