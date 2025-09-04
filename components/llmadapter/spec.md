# LLMAdapter — Contract-Driven Spec (v0.1)

> Project: lbp3-rs (FastAPI remote server for a RAG chat app)  
> Priorities: Testability + Observability + Swap-able internals (ports/adapters)  
> Status: First iteration (spec + contracts + HTTP edges + in-memory impl + tests)

## 1) Purpose
Provide an abstract, provider-agnostic interface to call Large Language Models (LLMs) for:
- Chat/completions (non-stream + stream)
- (Optional) Tool calling / function calling
- (Optional) Logit bias, system prompts, temperature, top-p, stop sequences, etc.

The adapter exposes a narrow, stable contract (`ports`) so that providers (OpenAI, Anthropic, etc.) are swappable behind the same API. It focuses on deterministic tests (via Fake provider) and strong runtime validation.

## 2) Responsibilities
- Validate inputs with Pydantic contracts.
- Normalize provider-specific request/response formats to a single UWF-style schema.
- Provide sync-ish (awaitable) non-stream and async streaming APIs.
- Attach trace/log context to each call for observability (span_id, request_id).
- Enforce configured limits (max tokens, max messages length).
- Surface provider/transport errors as typed domain errors.

## 3) Non-Responsibilities
- Orchestration of multi-turn chat memory (that’s ChatService’s job).
- Vector search / grounding (that’s Search/Indexer).
- Authentication and rate-limiting (ApiGateway/RateLimiter).

## 4) Ports (Contracts)
- `LLMProvider` (port): `generate()` and `stream()` with normalized inputs/outputs.
- Schemas:
  - `PromptMessage` (role + content + optional name + tool_call_id)
  - `ToolSpec` (optional)
  - `ChatRequest` (model, messages, sampling params, tool specs)
  - `ChatResponse` (id, model, content, finish_reason, usage, tool_calls[])
  - `ChatDelta` (for streaming: content delta, tool_calls delta, usage partials)
- Error types:
  - `LLMError` base; `ProviderError`, `RateLimitError`, `InvalidRequestError`, `AuthError`, `TimeoutError`.

## 5) HTTP Edges (FastAPI)
- `POST /v1/llm/chat` → non-stream response (`ChatResponse` JSON)
- `POST /v1/llm/chat/stream` → newline-delimited JSON chunks (`ChatDelta` … ends with `{"event":"end"}`)

Headers:
- `X-Request-Id` propagated if present; otherwise generated.

## 6) Observability
- Log fields: `request_id`, `span_id`, `tenant_id`, `user_id`, `provider`, `model`, perf timings (queue_ms, ttfb_ms, total_ms), token usage.
- (Future) OpenTelemetry spans around provider calls.

## 7) Configuration
- `LLM_PROVIDER`: `fake` (default), `openai`, `anthropic`
- Provider-specific keys via env:
  - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Limits:
  - `LLM_MAX_TOKENS_DEFAULT`, `LLM_TEMPERATURE_DEFAULT`

## 8) Security & Multi-Tenancy
- Upstream components must pass tenant/user scopes; adapter is stateless but logs tenant_id (if present) for traceability.
- Redact prompts in logs if `REDACT_PROMPTS=true`.

## 9) Storage
- None (stateless). Usage metrics can be emitted as events (future).

## 10) Testability
- Fake/Echo provider returns deterministic content for golden tests.
- Contract tests validate pydantic schemas + edge behavior (stream terminates with `end` event).

## 11) TODOs / Next Iterations
- [ ] Implement OpenAI provider (chat.completions) with retry/backoff.
- [ ] Implement Anthropic provider (Messages API) with tool use.
- [ ] Add function/tool calling output schema and demo tool roundtrip.
- [ ] Add OpenTelemetry spans + metrics (tokens, latency).
- [ ] Add per-tenant model/limits policy checks.

```python
