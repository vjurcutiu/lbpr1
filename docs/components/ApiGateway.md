# ApiGateway (layer: interface)

**Python package**: `app.interface.api`

**Responsibilities**

- FastAPI app; routing; OpenAPI
- AuthN/AuthZ middleware; request shaping
- Rate limiting; per-tenant context

**Provides**

HTTP:
- `GET /v1/health`
  - returns: `{'status': 200, 'body': {'ok': 'bool', 'version': 'string'}}`
- `POST /v1/auth/token`
  - in: `application/json`
  - returns: `{'status': 200, 'body': {'access_token': 'string', 'expires_in': 'int'}}`
- `POST /v1/files`
  - in: `multipart/form-data`
  - returns: `{'status': 202, 'body': {'job_id': 'string'}}`
  - invariant: file<=50MB
  - invariant: allowed content-type
- `GET /v1/search`
  - params: `{'q': 'string', 'limit': 'int=10'}`
  - returns: `{'status': 200, 'body': 'SearchResults'}`
- `POST /v1/chat`
  - in: `application/json`
  - returns: `{'status': 200, 'body': 'ChatResponse'}`
- `GET /v1/jobs/{id}`
  - returns: `{'status': 200, 'body': 'JobStatus'}`
WebSockets:
- path: /v1/events in=ClientEvent out=ServerEvent

**Invariants**

- Bearer required except /v1/health and /v1/auth/token
- Never import infrastructure or domain directly

**Forbidden imports**

- `app.infrastructure`
- `app.domain`

