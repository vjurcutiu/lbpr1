# /scripts/generate_contracts.py
"""
Reads /contracts/components.yaml and generates:
- /docs/diagrams/c4/structurizr.dsl          (C4 model)
- /docs/diagrams/mermaid/*.mmd               (sequence diagrams per flow)
- /docs/components/*.md                      (component pages)
- /architecture/importlinter.ini             (Python boundary enforcement)

Deps: pyyaml (pip install pyyaml)
Optional: import-linter (for CI enforcement)
"""
from __future__ import annotations
import os
import textwrap
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "contracts" / "components.yaml"
DOCS = ROOT / "docs"
C4_DIR = DOCS / "diagrams" / "c4"
MM_DIR = DOCS / "diagrams" / "mermaid"
COMP_DIR = DOCS / "components"
ARCH_DIR = ROOT / "architecture"

UserActorName = "User"


def ensure_dirs():
    for d in (DOCS, C4_DIR, MM_DIR, COMP_DIR, ARCH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_model() -> dict:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_structurizr(model: dict) -> str:
    system = model.get("system", "System")
    components = model.get("components", [])
    # Map component names to simple types for the diagram
    def container_line(c):
        name = c["name"]
        layer = c.get("layer", "component")
        tech = c.get("package", c.get("layer", ""))
        return f'      container "{name}" "{tech}" "{layer}"\n'

    # Relationships inferred from flows and consumes/provides
    rels = []
    for c in components:
        src = c["name"]
        # consumes http_from: ApiGateway → relation
        consumes = c.get("consumes", {})
        if isinstance(consumes, dict) and "http_from" in consumes:
            rels.append((consumes["http_from"], src, "calls"))
        # provides/consumes queues
        for q in consumes.get("commands", []) or []:
            rels.append((src, q.get("queue", "?"), "consumes"))

    # Also infer from flows for more realistic edges
    for flow in model.get("flows", []) or []:
        steps = flow.get("steps", [])
        for s in steps:
            a, b = s.get("from"), s.get("to")
            if a and b:
                # Skip user→component being added twice
                rels.append((a, b, ""))

    # Build DSL
    lines = []
    lines.append(f'workspace "{system}" {{\n')
    lines.append("  model {\n")
    lines.append("    person User\n")
    lines.append(f'    softwareSystem "{system}" {{\n')
    for c in components:
        lines.append(container_line(c))
    # relationships
    # Collapse into unique set
    seen = set()
    for a, b, label in rels:
        if (a, b, label) in seen:
            continue
        seen.add((a, b, label))
        if a == UserActorName:
            lines.append(f'      User -> "{b}" "{label or ""}"\n')
        else:
            lines.append(f'      "{a}" -> "{b}" "{label or ""}"\n')
    lines.append("    }\n")
    lines.append("  }\n")
    lines.append("  views {\n")
    lines.append(f'    container "{system}" {{\n')
    lines.append("      include *\n      autoLayout\n    }\n")
    lines.append("  }\n")
    lines.append("}\n")
    return "".join(lines)


def to_mermaid_sequences(model: dict) -> dict[str, str]:
    out = {}
    for flow in model.get("flows", []) or []:
        name = flow.get("name", "Flow")
        steps = flow.get("steps", [])
        participants = set()
        for s in steps:
            participants.add(s.get("from"))
            participants.add(s.get("to"))
        participants.discard(None)
        # Build diagram
        lines = ["sequenceDiagram\n"]
        # Actors/participants
        for p in sorted(participants):
            if p == UserActorName:
                lines.append(f"  actor {p}\n")
            else:
                alias = p.replace(" ", "")[:10]
                lines.append(f"  participant {alias} as {p}\n")
        # Messages
        for s in steps:
            a, b, note = s.get("from"), s.get("to"), s.get("note", "")
            if a and b:
                a_alias = a if a == UserActorName else a.replace(" ", "")[:10]
                b_alias = b if b == UserActorName else b.replace(" ", "")[:10]
                lines.append(f"  {a_alias}->>{b_alias}: {note}\n")
        out[name] = "".join(lines)
    return out


def component_markdown(c: dict, layers: dict) -> str:
    name = c["name"]
    layer = c.get("layer", "")
    package = c.get("package", "")
    resp = c.get("responsibilities", []) or []
    provides = c.get("provides", {}) or {}
    consumes = c.get("consumes", {}) or {}
    invariants = c.get("invariants", []) or []
    forbidden = c.get("forbidden_imports", []) or []

    md = [f"# {name} (layer: {layer})\n\n"]
    if package:
        md.append(f"**Python package**: `{package}`\n\n")
    if resp:
        md.append("**Responsibilities**\n\n")
        for r in resp:
            md.append(f"- {r}\n")
        md.append("\n")
    if provides:
        md.append("**Provides**\n\n")
        if "http" in provides:
            md.append("HTTP:\n")
            for ep in provides["http"]:
                method = ep.get("method", "").upper()
                path = ep.get("path", "")
                md.append(f"- `{method} {path}`\n")
                if ep.get("params"):
                    md.append(f"  - params: `{ep['params']}`\n")
                if ep.get("out"):
                    md.append(f"  - returns: `{ep['out']}`\n")
                if ep.get("invariants"):
                    for inv in ep["invariants"]:
                        md.append(f"  - invariant: {inv}\n")
        if "commands" in provides:
            md.append("Commands:\n")
            for q in provides["commands"]:
                md.append(f"- queue: {q.get('queue')} message: {q.get('message')}\n")
        if "events" in provides:
            md.append("Events:\n")
            for e in provides["events"]:
                md.append(f"- topic: {e.get('topic')} message: {e.get('message')}\n")
        if "queries" in provides:
            md.append("Queries:\n")
            for q in provides["queries"]:
                md.append(f"- {q.get('name')} in={q.get('in')} out={q.get('out')}\n")
        md.append("\n")
    if consumes:
        md.append("**Consumes**\n\n")
        if "http_from" in consumes:
            md.append(f"- http_from: {consumes['http_from']}\n")
        for kind in ("commands", "events"):
            if kind in consumes:
                for item in consumes[kind]:
                    md.append(f"- {kind.rstrip('s')}: {item}\n")
        md.append("\n")
    if invariants:
        md.append("**Invariants**\n\n")
        for inv in invariants:
            md.append(f"- {inv}\n")
        md.append("\n")
    if forbidden:
        md.append("**Forbidden imports**\n\n")
        for f in forbidden:
            md.append(f"- `{f}`\n")
        md.append("\n")
    return "".join(md)


def to_import_linter(model: dict) -> str:
    layers = model.get("layers", [])
    components = model.get("components", [])

    # Build layer order for a classic interface→app→domain→infra rule
    ordered = [l["pkg"] for l in layers]
    ordered = ",\n    ".join(ordered)

    lines = ["[importlinter]\n", "root_package = app\n\n"]
    lines.append("[contracts.layering]\n")
    lines.append("type = layers\n")
    lines.append("layers =\n    ")
    lines.append(ordered + "\n\n")

    # Forbidden imports per component
    idx = 1
    for c in components:
        forb = c.get("forbidden_imports", []) or []
        src_pkg = c.get("package") or c.get("name")
        if forb:
            lines.append(f"[contracts.forbidden_{idx}]\n")
            lines.append("type = forbidden\n")
            lines.append(f"source_modules =\n    {src_pkg}\n")
            lines.append("forbidden_modules =\n")
            for f in forb:
                lines.append(f"    {f}\n")
            lines.append("\n")
            idx += 1
    return "".join(lines)


def main():
    ensure_dirs()
    model = load_model()

    # 1) Structurizr DSL
    structurizr = to_structurizr(model)
    (C4_DIR / "structurizr.dsl").write_text(structurizr, encoding="utf-8")

    # 2) Mermaid sequences per flow
    for name, mmd in to_mermaid_sequences(model).items():
        (MM_DIR / f"{name}.mmd").write_text(mmd, encoding="utf-8")

    # 3) Component pages
    layers_map = {l["name"]: l for l in model.get("layers", [])}
    for c in model.get("components", []) or []:
        md = component_markdown(c, layers_map)
        (COMP_DIR / f"{c['name']}.md").write_text(md, encoding="utf-8")

    # 4) Import Linter config
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    (ARCH_DIR / "importlinter.ini").write_text(to_import_linter(model), encoding="utf-8")

    # 5) Root docs index (simple)
    index_md = [f"# {model.get('system', 'System')} — Architecture\n\n"]
    index_md.append("## Components\n\n")
    for c in model.get("components", []) or []:
        index_md.append(f"- [{c['name']}](./components/{c['name']}.md)\n")
    index_md.append("\n## Diagrams\n\n")
    index_md.append("- [C4 model](./diagrams/c4/structurizr.dsl)\n")
    for flow in model.get("flows", []) or []:
        nm = flow.get("name")
        index_md.append(f"- {nm} (Mermaid): ./diagrams/mermaid/{nm}.mmd\n")
    (DOCS / "index.md").write_text("".join(index_md), encoding="utf-8")

    print("Generated: Structurizr DSL, Mermaid flows, component docs, importlinter.ini")


if __name__ == "__main__":
    main()