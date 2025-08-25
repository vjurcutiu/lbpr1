# Indexer (layer: domain)

**Python package**: `app.domain.indexer`

**Responsibilities**

- Text extraction -> chunk -> embed -> upsert to vector store

**Provides**

Events:
- topic: indexing-completed message: IndexResult

**Consumes**

- command: {'queue': 'indexing-jobs', 'message': 'IndexJob'}

**Invariants**

- Chunk size = 1500 tokens ±10%
- Retry policy: 3 attempts with exponential backoff

