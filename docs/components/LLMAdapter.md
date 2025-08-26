# LLMAdapter (layer: infrastructure)

**Python package**: `app.infrastructure.llm`

**Responsibilities**

- LLM completion calls used by ChatService & MetadataService
- Prompt/response logging with redaction

**Invariants**

- Do not store raw prompts with PII
- Configurable model + temperature

