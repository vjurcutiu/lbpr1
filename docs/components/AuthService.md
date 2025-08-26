# AuthService (layer: application)

**Python package**: `app.application.auth`

**Responsibilities**

- Validate API keys/JWT; issue access tokens
- Inject sub/tenant/scopes into request context

**Provides**

Queries:
- validateToken in={'token': 'string'} out={'valid': 'bool', 'sub': 'string', 'tenant_id': 'string', 'scopes': 'array<string>'}

**Invariants**

- Clock skew ≤ 60s
- TTL ≤ 1h

