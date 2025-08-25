# Contracts-as-Source Architecture — How To Use

This repo treats **contracts as the single source of truth**. One YAML file (`/contracts/components.yaml`) defines components, boundaries, APIs, invariants, and flows. A generator emits diagrams, component docs, and an **Import Linter** config that enforces boundaries in Python code.

## Quick Start

1. Edit `/contracts/components.yaml` to match your system.
2. Run `make setup && make contracts` to generate docs & configs.
3. Run `make lint-architecture` to enforce boundaries.
4. Commit generated files under `/docs/**` and `/architecture/importlinter.ini`.

## Conventions

- **Layers**: interface → application → domain → infrastructure.
- **Packages**: each component maps to a Python package, e.g., `app.domain.search`.
- **APIs**: define REST in `/openapi/api.yaml` (or auto-export from FastAPI) and link from component docs.
- **Messages/Schemas**: place JSON Schema or Pydantic exports in `/schemas/`.
- **Flows**: put critical sequences in the YAML under `flows:` — generator creates Mermaid diagrams.

## CI Gate (Optional)

Use the provided GitHub Action to:
- regenerate diagrams on each PR,
- fail the build on boundary violations.

## Local Diagram Rendering

- **C4**: Open `docs/diagrams/c4/structurizr.dsl` in Structurizr Lite (Docker) for beautiful layouts.
- **Mermaid**: View `.mmd` files in VS Code with Mermaid extension or render on GitHub.

## Evolving the System

- Change the YAML → run `make contracts` → review the diff in `/docs/**` → update code.
- Treat `/contracts/components.yaml` like code: PRs, reviews, and versioning.

## Tips

- Keep components cohesive; a component should have 1–3 clear responsibilities.
- Push adapters (Pinecone, S3, DB) to **infrastructure**; keep business rules in **domain**.
- For stricter correctness (concurrency, invariants), add **TLA+** or **Alloy** specs per critical flow; keep them under `/specs/formal/` (not included here).

---

© You. Reuse this template freely in future projects.