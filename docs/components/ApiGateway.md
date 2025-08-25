# ApiGateway (layer: interface)

**Python package**: `app.interface.api`

**Responsibilities**

- FastAPI app; routing; authn/authz middleware

**Provides**

HTTP:
- `POST /upload`
  - returns: `{'status': 202, 'body': {'job_id': 'string'}}`
  - invariant: File <= 50MB
  - invariant: User authenticated
- `GET /search`
  - params: `{'q': 'string', 'limit': 'int=10'}`
  - returns: `{'status': 200, 'body': 'SearchResults'}`

**Consumes**

- command: {'queue': 'indexing-jobs', 'message': 'IndexJob'}

**Invariants**

- Never touches storage or vector store directly; uses application services only

**Forbidden imports**

- `app.infrastructure`
- `app.domain`

