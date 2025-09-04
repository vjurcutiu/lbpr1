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