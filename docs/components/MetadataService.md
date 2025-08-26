# MetadataService (layer: domain)

**Python package**: `app.domain.metadata`

**Responsibilities**

- AI metadata generation for documents: title/summary/keywords/topics
- Quality heuristics; language detection

**Provides**

Queries:
- generateMetadata in={'tenant_id': 'string', 'file_id': 'string'} out=MetadataRecord

**Invariants**

- Use LLMAdapter; deterministic temperature for metadata
- Attach metadata to document record prior to chunking

