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