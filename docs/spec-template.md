## <ComponentName> — Contract

### Purpose
(One paragraph: what this component owns, what it does **not** do.)

### Package / Layer
- Package: `app.<layer>.<name>`
- Layer: <interface|application|domain|infrastructure>

### Dependencies (ports only)
- Uses ports:
  - `FooPort` (what for, latency/throughput expectations)
  - `BarPort` (…)
- Must not import: (if any; enforce with import-linter)

### Inputs (public API)
- Function(s):
  - `fn signature`  
    - **Input schema** (Pydantic model or typed args): (link/type)
    - **Preconditions** (validation rules)
    - **Idempotency** rules (if any)

### Outputs
- **Return type** (link/type)
- **Postconditions** (must be true on return)

### Errors (typed)
- Enumerate error conditions → **typed exceptions** with codes.
  - `ValidationError("too_long")` when …
  - `DependencyError("llm_timeout")` when …

### Invariants
- Bullet list of rules that must always hold.
  - “Never send raw PII to LLM”
  - “Include citations for every grounded snippet”
  - …

### Observability
- Log/traces/metrics that **must** be emitted (schema-level promises).

### Tests (must pass)
- Contract tests:
  - Happy path(s) with fixed inputs → fixed outputs (golden or matchers)
  - Boundary cases (min/max, empty, non-ASCII)
  - Error cases (timeouts, missing deps)
- Property tests (if applicable)
- Performance budget (optional): p95 ≤ N ms with fakes
