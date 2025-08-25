# /scripts/generate_contracts.py
"""
Reads /contracts/components.yaml and generates:
- /docs/diagrams/c4/structurizr.dsl          (C4 model)
- /docs/diagrams/c4/c4.puml                  (C4-PlantUML)
- /docs/diagrams/mermaid/*.mmd               (sequence diagrams per flow)
- /docs/components/*.md                      (component pages)
- /architecture/importlinter.ini             (Python boundary enforcement)

Deps: pyyaml (pip install pyyaml)
Optional: import-linter (for CI enforcement)
"""
from __future__ import annotations
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "contracts" / "components.yaml"
DOCS = ROOT / "docs"
C4_DIR = DOCS / "diagrams" / "c4"
MM_DIR = DOCS / "diagrams" / "mermaid"
COMP_DIR = DOCS / "components"
ARCH_DIR = ROOT / "architecture"

USER_ACTOR_NAME = "User"


def ensure_dirs() -> None:
    for d in (DOCS, C4_DIR, MM_DIR, COMP_DIR, ARCH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_model() -> dict:
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# -------------------------------
# Structurizr DSL (unchanged)
# -------------------------------
def to_structurizr(model: dict) -> str:
    system = model.get("system", "System")
    components = model.get("components", [])

    def container_line(c: dict) -> str:
        name = c["name"]
        layer = c.get("layer", "component")
        tech = c.get("package", c.get("layer", ""))
        return f'      container "{name}" "{tech}" "{layer}"\n'

    rels: list[tuple[str, str, str]] = []
    for c in components:
        src = c["name"]
        consumes = c.get("consumes", {})
        if isinstance(consumes, dict) and "http_from" in consumes:
            rels.append((consumes["http_from"], src, "calls"))
        for q in consumes.get("commands", []) or []:
            rels.append((src, q.get("queue", "?"), "consumes"))

    for flow in model.get("flows", []) or []:
        for s in flow.get("steps", []):
            a, b = s.get("from"), s.get("to")
            if a and b:
                rels.append((a, b, ""))

    lines: list[str] = []
    lines.append(f'workspace "{system}" {{\n')
    lines.append("  model {\n")
    lines.append("    person User\n")
    lines.append(f'    softwareSystem "{system}" {{\n')
    for c in components:
        lines.append(container_line(c))
    seen = set()
    for a, b, label in rels:
        key = (a, b, label)
        if key in seen:
            continue
        seen.add(key)
        if a == USER_ACTOR_NAME:
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


# -------------------------------
# Mermaid sequence diagrams
# -------------------------------
def to_mermaid_sequences(model: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for flow in model.get("flows", []) or []:
        name = flow.get("name", "Flow")
        steps = flow.get("steps", [])
        participants = set()
        for s in steps:
            participants.add(s.get("from"))
            participants.add(s.get("to"))
        participants.discard(None)
        lines = ["sequenceDiagram\n"]
        for p in sorted(participants):
            if p == USER_ACTOR_NAME:
                lines.append(f"  actor {p}\n")
            else:
                alias = _alias(p)
                lines.append(f"  participant {alias} as {p}\n")
        for s in steps:
            a, b, note = s.get("from"), s.get("to"), s.get("note", "")
            if a and b:
                a_alias = a if a == USER_ACTOR_NAME else _alias(a)
                b_alias = b if b == USER_ACTOR_NAME else _alias(b)
                lines.append(f"  {a_alias}->>{b_alias}: {note}\n")
        out[name] = "".join(lines)
    return out


def _alias(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name)[:12] or "X"


# -------------------------------
# Component Markdown
# -------------------------------
def component_markdown(c: dict) -> str:
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


# -------------------------------
# Import Linter config
# -------------------------------
def to_import_linter(model: dict) -> str:
    layers = model.get("layers", [])
    components = model.get("components", [])
    ordered = ",\n    ".join(l["pkg"] for l in layers)

    lines = ["[importlinter]\n", "root_package = app\n\n"]
    lines.append("[contracts.layering]\n")
    lines.append("type = layers\n")
    lines.append("layers =\n    ")
    lines.append(ordered + "\n\n")

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


# -------------------------------
# C4-PlantUML emitter (NEW)
# -------------------------------
def to_c4_plantuml(model: dict) -> str:
    """
    Emits a single C4 container-level diagram using C4-PlantUML.
    Renders:
      - Person(User)
      - System_Boundary with one Container per component
      - Relations inferred from flows and simple consumes
    """
    system = model.get("system", "System")
    components = model.get("components", [])

    # Helper: stable IDs for PlantUML
    def cid(name: str) -> str:
        # letters/digits/underscore; lowercase to keep consistent
        ident = re.sub(r"[^A-Za-z0-9_]", "_", name)
        ident = re.sub(r"_+", "_", ident).strip("_")
        return (ident or "C").lower()

    # Gather relationships (like Structurizr)
    rels: set[tuple[str, str, str]] = set()
    for c in components:
        src = c["name"]
        consumes = c.get("consumes", {})
        if isinstance(consumes, dict) and "http_from" in consumes:
            rels.add((consumes["http_from"], src, "calls"))
        for q in consumes.get("commands", []) or []:
            rels.add((src, q.get("queue", "?"), "consumes"))

    for flow in model.get("flows", []) or []:
        for s in flow.get("steps", []):
            a, b = s.get("from"), s.get("to")
            if a and b:
                rels.add((a, b, ""))

    # Build PUML
    lines: list[str] = []
    lines.append("@startuml\n")
    # Pull the C4 include from the official repo (no local files needed)
    lines.append("!includeurl https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4.puml\n\n")
    lines.append("LAYOUT_WITH_LEGEND()\n\n")
    lines.append(f'Person({cid(USER_ACTOR_NAME)}, "{USER_ACTOR_NAME}")\n')
    lines.append(f'System_Boundary(sys, "{system}") {{\n')

    # Emit containers
    for c in components:
        _id = cid(c["name"])
        name = c["name"]
        tech = c.get("package", c.get("layer", ""))
        desc = "; ".join(c.get("responsibilities", []) or [])[:180]
        tech_label = f"{tech}" if tech else ""
        # Container(id, "Name", "Tech", "Desc")
        lines.append(f'  Container({_id}, "{_escape(name)}", "{_escape(tech_label)}", "{_escape(desc)}")\n')

    lines.append("}\n\n")

    # Emit relations
    for a, b, label in sorted(rels):
        a_id = cid(a)
        b_id = cid(b)
        if a == USER_ACTOR_NAME:
            lines.append(f"Rel({cid(USER_ACTOR_NAME)}, {b_id}, \"{_escape(label)}\")\n")
        else:
            # Only relate if both ends are known or from user/queue
            lines.append(f"Rel({a_id}, {b_id}, \"{_escape(label)}\")\n")

    lines.append("\n@enduml\n")
    return "".join(lines)


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')

THEMES = {
    "dark": [
        "skinparam backgroundColor #141414",
        "skinparam defaultFontColor #FFFFFF",
        "skinparam defaultTextAlignment center",
        "",
        "' Components",
        "skinparam RectangleBackgroundColor #2c3e50",
        "skinparam RectangleBorderColor #3498db",
        "skinparam RectangleFontColor #FFFFFF",
        "",
        "skinparam DatabaseBackgroundColor #2c3e50",
        "skinparam DatabaseBorderColor #3498db",
        "skinparam DatabaseFontColor #FFFFFF",
        "",
        "' Actors",
        "skinparam ActorBackgroundColor #141414",
        "skinparam ActorBorderColor #FFFFFF",
        "skinparam ActorFontColor #FFFFFF",
        "",
        "' Relations",
        "skinparam ArrowColor #FFFFFF",
        "skinparam ArrowThickness 2",
    ],
    "light": [
        "skinparam backgroundColor #FFFFFF",
        "skinparam defaultFontColor #000000",
        "skinparam defaultTextAlignment center",
        "",
        "' Components",
        "skinparam RectangleBackgroundColor #e8f4ff",
        "skinparam RectangleBorderColor #2980b9",
        "skinparam RectangleFontColor #000000",
        "",
        "skinparam DatabaseBackgroundColor #fef9e7",
        "skinparam DatabaseBorderColor #f1c40f",
        "skinparam DatabaseFontColor #000000",
        "",
        "' Actors",
        "skinparam ActorBackgroundColor #FFFFFF",
        "skinparam ActorBorderColor #000000",
        "skinparam ActorFontColor #000000",
        "",
        "' Relations",
        "skinparam ArrowColor #000000",
        "skinparam ArrowThickness 2",
    ],
}


def to_plain_plantuml(model: dict, theme: str = "dark") -> str:
    """
    Self-contained PlantUML (no external includes).
    Renders: a person, a system boundary, one node per component, and relations.
    """
    import re
    system = model.get("system", "System")
    components = model.get("components", [])
    flows = model.get("flows", []) or []

    def pid(name: str) -> str:
        s = re.sub(r"[^A-Za-z0-9_]", "_", name)
        s = re.sub(r"_+", "_", s).strip("_")
        return (s or "X")[:24]

    # Collect relations (like we did for Structurizr)
    rels = set()
    for c in components:
        src = c["name"]
        consumes = c.get("consumes", {}) or {}
        if "http_from" in consumes:
            rels.add((consumes["http_from"], src, "calls"))
        for q in consumes.get("commands", []) or []:
            rels.add((src, q.get("queue", "?"), "consumes"))
    for f in flows:
        for s in f.get("steps", []):
            a, b = s.get("from"), s.get("to")
            if a and b: rels.add((a, b, s.get("note", "")))

    out = []
    out.append("@startuml\n")
    for line in THEMES.get(theme, THEMES["dark"]):
        out.append(line + "\n")
    out.append("\n")

    out.append(f'package "{system}" as {pid(system)} {{\n')
    for c in components:
        cid = pid(c["name"])
        name = c["name"]
        tech = c.get("package", c.get("layer", ""))
        # Choose a shape: database if adapter mentions db/blob, else rectangle
        shape = "database" if "db" in tech.lower() or "blob" in tech.lower() or "store" in tech.lower() else "rectangle"
        out.append(f'  {shape} "{name}\\n[{tech}]" as {cid}\n')
    out.append("}\n\n")

    for a, b, label in sorted(rels):
        a_id = pid(a)
        b_id = pid(b)
        if a == "User":
            out.append(f"{pid('User')} --> {b_id} : {label}\n")
        else:
            out.append(f"{a_id} --> {b_id} : {label}\n")

    out.append("@enduml\n")
    return "".join(out)



# -------------------------------
# Main
# -------------------------------
def main() -> None:
    ensure_dirs()
    model = load_model()

    # 1) Structurizr DSL
    (C4_DIR / "structurizr.dsl").write_text(to_structurizr(model), encoding="utf-8")

    # 2) C4-PlantUML
    (C4_DIR / "c4.puml").write_text(to_c4_plantuml(model), encoding="utf-8")

    # 2b) Plain PlantUML (no includes)
    (C4_DIR / "c4_plain_dark.puml").write_text(to_plain_plantuml(model, "dark"), encoding="utf-8")
    (C4_DIR / "c4_plain_light.puml").write_text(to_plain_plantuml(model, "light"), encoding="utf-8")

    # 3) Mermaid sequences per flow
    for name, mmd in to_mermaid_sequences(model).items():
        (MM_DIR / f"{name}.mmd").write_text(mmd, encoding="utf-8")

    # 4) Component pages
    for c in model.get("components", []) or []:
        (COMP_DIR / f"{c['name']}.md").write_text(component_markdown(c), encoding="utf-8")

    # 5) Import Linter config
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    (ARCH_DIR / "importlinter.ini").write_text(to_import_linter(model), encoding="utf-8")

    # 6) Root docs index
    index_md = [f"# {model.get('system', 'System')} — Architecture\n\n"]
    index_md.append("## Components\n\n")
    for c in model.get("components", []) or []:
        index_md.append(f"- [{c['name']}](./components/{c['name']}.md)\n")
    index_md.append("\n## Diagrams\n\n")
    index_md.append("- [C4 model (Structurizr DSL)](./diagrams/c4/structurizr.dsl)\n")
    index_md.append("- [C4 model (PlantUML)](./diagrams/c4/c4.puml)\n")
    for flow in model.get("flows", []) or []:
        nm = flow.get("name")
        index_md.append(f"- {nm} (Mermaid): ./diagrams/mermaid/{nm}.mmd\n")
    (DOCS / "index.md").write_text("".join(index_md), encoding="utf-8")

    print("Generated: Structurizr DSL, C4-PlantUML, Mermaid flows, component docs, importlinter.ini")


if __name__ == "__main__":
    main()
