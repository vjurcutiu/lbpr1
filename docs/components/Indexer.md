# Indexer (layer: domain)

**Python package**: `app.domain.indexer`

**Responsibilities**

- Extract text → chunk → embed → upsert to vector store
- Coordinate with MetadataService for enriched fields

**Provides**

Events:
- topic: jobs message: IndexResult

**Consumes**

- command: {'queue': 'ingestion-jobs', 'message': 'IndexJob'}

**Invariants**

- Chunk size 1500 ±10%
- Retries: 3 with exponential backoff
- All vectors are namespace-per-tenant

