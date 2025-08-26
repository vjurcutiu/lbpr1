# RateLimiter (layer: application)

**Python package**: `app.application.ratelimit`

**Responsibilities**

- Sliding window rate limits per tenant/key

**Provides**

Queries:
- checkAndConsume in={'key': 'string', 'cost': 'int=1'} out={'allowed': 'bool', 'remaining': 'int'}

