# IngestionService (layer: application)

**Python package**: `app.application.ingestion`

**Responsibilities**

- Validate file; compute checksum; create IndexJob; enqueue

**Provides**

Commands:
- queue: indexing-jobs message: IndexJob

**Consumes**

- http_from: ApiGateway

**Invariants**

- Reject files > 50MB
- Idempotent jobs (same checksum => no duplicate)

