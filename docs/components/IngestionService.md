# IngestionService (layer: application)

**Python package**: `app.application.ingestion`

**Responsibilities**

- Validate upload; compute checksum
- Persist raw file to blob storage
- Emit IndexJob to queue

**Provides**

Commands:
- queue: ingestion-jobs message: IndexJob

**Consumes**

- http_from: ApiGateway

**Invariants**

- Idempotent on (tenant_id, checksum)
- Reject > 50MB

