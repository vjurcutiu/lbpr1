# ChatService (layer: domain)

**Python package**: `app.domain.chat`

**Responsibilities**

- RAG chat orchestration: retrieve context → synthesize answer with LLM
- Streaming support (partial deltas) via WS events
- Citations and safety filters

**Provides**

Queries:
- chat in=ChatRequest out=ChatResponse

**Consumes**

- http_from: ApiGateway

**Invariants**

- Always perform retrieval before answer unless user instructs otherwise
- Citations include document IDs and spans
- Redact secrets from prompts

