# SearchService (layer: domain)

**Python package**: `app.domain.search`

**Responsibilities**

- Hybrid search (keyword + vector) and ranking per tenant
- Return results with metadata & citation source references

**Provides**

Queries:
- search in={'q': 'string', 'limit': 'int=10', 'tenant_id': 'string'} out=SearchResults

**Invariants**

- Latency p95 ≤ 800ms @ 50 conc/tenant

