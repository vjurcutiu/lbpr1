# /scripts/generate_contracts.py
"""
Reads /contracts/components.toml and generates:
- /docs/diagrams/c4/structurizr.dsl          (Structurizr DSL)
- /docs/diagrams/mermaid/*.mmd               (sequence diagrams per flow)
- /docs/components/*.md                      (component pages)
- /architecture/importlinter.ini             (Python boundary enforcement)
- /docs/diagrams/c4/c4_plain_{dark,light}.puml (self-contained PlantUML)

Deps:
  - Python 3.11+ (uses tomllib). For 3.10 or earlier: pip install tomli and it will be imported.
"""

from __future__ import annotations
import os
from pathlib import Path
import re
import textwrap

# --- TOML loader --------------------------------------------------------------
try:
    import tomllib  # Py 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_TOML = ROOT / "contracts" / "components.toml"

DOCS = ROOT / "docs"
C4_DIR = DOCS / "diagrams" / "c4"
MM_DIR = DOCS / "diagrams" / "mermaid"
COMP_DIR = DOCS / "components"
ARCH_DIR = ROOT / "architecture"

USER = "User"


# --- Helpers: filesystem ------------------------------------------------------
def ensure_dirs() -> None:
    for d in (DOCS, C4_DIR, MM_DIR, COMP_DIR, ARCH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_model() -> dict:
    if not CONTRACTS_TOML.exists():
        raise FileNotFoundError(f"Missing {CONTRACTS_TOML}")
    with open(CONTRACTS_TOML, "rb") as f:
        model = tomllib.load(f) or {}
    # debug line; helpful during tasks troubleshooting
    print(f"[contracts] loaded: {CONTRACTS_TOML}")
    print(f"[contracts] system: {model.get('system')}")
    return model


# --- Normalization: accept both dict and list-of-dicts for nested sections ----
def _merge_list_of_dicts(items):
    merged = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for k, v in item.items():
            # for list-typed keys (commands/events/websockets/http/queries) we append
            if isinstance(v, list) and k in ("commands", "events", "websockets", "http", "queries"):
                merged.setdefault(k, [])
                merged[k].extend(v)
            else:
                merged[k] = v
    return merged


def norm_section(sec):
    """
    Accept either:
      - dict-like (TOML table)
      - list of dicts (TOML array of tables)
    Return a single dict with list keys combined.
    """
    if sec is None:
        return {}
    if isinstance(sec, dict):
        return sec
    if isinstance(sec, list):
        return _merge_list_of_dicts(sec)
    return {}


def norm_component(c: dict) -> dict:
    c = dict(c)  # shallow copy
    c["provides"] = norm_section(c.get("provides"))
    c["consumes"] = norm_section(c.get("consumes"))
    # ensure lists where expected
    for key in ("responsibilities", "invariants", "forbidden_imports"):
        if c.get(key) is None:
            c[key] = []
        elif not isinstance(c[key], list):
            c[key] = [c[key]]
    return c


def iter_components(model: dict):
    for c in model.get("components", []) or []:
        yield norm_component(c)


# --- Structurizr DSL ----------------------------------------------------------
def to_structurizr(model: dict) -> str:
    system = model.get("system", "System")
    components = list(iter_components(model))

    def container_line(c):
        name = c["name"]
        layer = c.get("layer", "component")
        tech = c.get("package", c.get("layer", ""))
        return f'      container "{name}" "{tech}" "{layer}"\n'

    rels = []

    # relationships from consumes/provides
    for c in components:
        src = c["name"]
        consumes = c.get("consumes", {})
        if isinstance(consumes, dict) and "http_from" in consumes:
            rels.append((consumes["http_from"], src, "calls"))
        # queues/events
        for q in consumes.get("commands", []) or []:
            qname = q.get("queue") or q.get("topic") or "queue"
            rels.append((src, qname, "consumes"))

    # infer from flows
    for flow in model.get("flows", []) or []:
        for s in flow.get("steps", []) or []:
            a, b = s.get("from"), s.get("to")
            if a and b:
                rels.append((a, b, s.get("note", "")))

    # Build DSL
    out = []
    out.append(f'workspace "{system}" {{\n')
    out.append("  model {\n")
    out.append("    person User\n")
    out.append(f'    softwareSystem "{system}" {{\n')
    for c in components:
        out.append(container_line(c))
    seen = set()
    for a, b, label in rels:
        key = (a, b, label or "")
        if key in seen:
            continue
        seen.add(key)
        if a == USER:
            out.append(f'      User -> "{b}" "{label or ""}"\n')
        else:
            out.append(f'      "{a}" -> "{b}" "{label or ""}"\n')
    out.append("    }\n")
    out.append("  }\n")
    out.append("  views {\n")
    out.append(f'    container "{system}" {{\n')
    out.append("      include *\n      autoLayout\n    }\n")
    out.append("  }\n")
    out.append("}\n")
    return "".join(out)


# --- Mermaid sequences --------------------------------------------------------
def to_mermaid_sequences(model: dict) -> dict[str, str]:
    diagrams = {}
    for flow in model.get("flows", []) or []:
        name = flow.get("name", "Flow")
        steps = flow.get("steps", []) or []

        participants = set()
        for s in steps:
            participants.add(s.get("from"))
            participants.add(s.get("to"))
        participants.discard(None)

        lines = ["sequenceDiagram\n"]
        for p in sorted(participants):
            if p == USER:
                lines.append("  actor User\n")
            else:
                alias = re.sub(r"\W+", "", p)[:12] or "X"
                lines.append(f"  participant {alias} as {p}\n")

        for s in steps:
            a, b, note = s.get("from"), s.get("to"), s.get("note", "")
            if not a or not b:
                continue
            a_alias = "User" if a == USER else re.sub(r"\W+", "", a)[:12]
            b_alias = "User" if b == USER else re.sub(r"\W+", "", b)[:12]
            lines.append(f"  {a_alias}->>{b_alias}: {note}\n")

        diagrams[name] = "".join(lines)
    return diagrams


# --- Component docs -----------------------------------------------------------
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
        if provides.get("http"):
            md.append("HTTP:\n")
            for ep in provides["http"]:
                method = ep.get("method", "").upper()
                path = ep.get("path", "")
                md.append(f"- `{method} {path}`\n")
                if ep.get("params"):
                    md.append(f"  - params: `{ep['params']}`\n")
                if ep.get("in"):
                    md.append(f"  - in: `{ep['in']}`\n")
                if ep.get("out"):
                    md.append(f"  - returns: `{ep['out']}`\n")
                if ep.get("invariants"):
                    for inv in ep["invariants"]:
                        md.append(f"  - invariant: {inv}\n")
        if provides.get("commands"):
            md.append("Commands:\n")
            for q in provides["commands"]:
                md.append(f"- queue: {q.get('queue')} message: {q.get('message')}\n")
        if provides.get("events"):
            md.append("Events:\n")
            for e in provides["events"]:
                md.append(f"- topic: {e.get('topic')} message: {e.get('message')}\n")
        if provides.get("queries"):
            md.append("Queries:\n")
            for q in provides["queries"]:
                md.append(f"- {q.get('name')} in={q.get('in')} out={q.get('out')}\n")
        if provides.get("websockets"):
            md.append("WebSockets:\n")
            for w in provides["websockets"]:
                md.append(f"- path: {w.get('path')} in={w.get('msg_in')} out={w.get('msg_out')}\n")
        md.append("\n")
    if consumes:
        md.append("**Consumes**\n\n")
        if "http_from" in consumes:
            md.append(f"- http_from: {consumes['http_from']}\n")
        for kind in ("commands", "events"):
            for item in consumes.get(kind, []) or []:
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


# --- Import Linter config -----------------------------------------------------
def to_import_linter(model: dict) -> str:
    layers = model.get("layers", [])
    components = list(iter_components(model))

    ordered = ",\n    ".join(l.get("pkg", l.get("name", "")) for l in layers)

    lines = ["[importlinter]\n", "root_package = app\n\n"]
    lines.append("[contracts.layering]\n")
    lines.append("type = layers\n")
    lines.append("layers =\n    " + ordered + "\n\n")

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


# --- Plain PlantUML (themes) --------------------------------------------------
THEMES = {
    "dark": [
        "skinparam backgroundColor #141414",
        "skinparam defaultFontColor #FFFFFF",
        "skinparam defaultTextAlignment center",
        "skinparam RectangleBackgroundColor #2c3e50",
        "skinparam RectangleBorderColor #5b95c7",
        "skinparam RectangleFontColor #FFFFFF",
        "skinparam DatabaseBackgroundColor #2c3e50",
        "skinparam DatabaseBorderColor #5b95c7",
        "skinparam DatabaseFontColor #FFFFFF",
        "skinparam ActorBackgroundColor #141414",
        "skinparam ActorBorderColor #FFFFFF",
        "skinparam ActorFontColor #FFFFFF",
        "skinparam ArrowColor #FFFFFF",
        "skinparam ArrowThickness 2",
    ],
    "light": [
        "skinparam backgroundColor #FFFFFF",
        "skinparam defaultFontColor #000000",
        "skinparam defaultTextAlignment center",
        "skinparam RectangleBackgroundColor #e8f4ff",
        "skinparam RectangleBorderColor #2980b9",
        "skinparam RectangleFontColor #000000",
        "skinparam DatabaseBackgroundColor #fef9e7",
        "skinparam DatabaseBorderColor #f1c40f",
        "skinparam DatabaseFontColor #000000",
        "skinparam ActorBackgroundColor #FFFFFF",
        "skinparam ActorBorderColor #000000",
        "skinparam ActorFontColor #000000",
        "skinparam ArrowColor #000000",
        "skinparam ArrowThickness 2",
    ],
}


def _pid(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "X")[:24]


def to_plain_plantuml(model: dict, theme: str = "dark") -> str:
    system = model.get("system", "System")
    comps = list(iter_components(model))

    # collect relations like DSL
    rels = set()
    for c in comps:
        src = c["name"]
        cons = c.get("consumes", {}) or {}
        if "http_from" in cons:
            rels.add((cons["http_from"], src, "calls"))
        for q in cons.get("commands", []) or []:
            rels.add((src, q.get("queue", "queue"), "consumes"))
    for f in model.get("flows", []) or []:
        for s in f.get("steps", []) or []:
            a, b = s.get("from"), s.get("to")
            if a and b:
                rels.add((a, b, s.get("note", "")))

    out = []
    out.append("@startuml\n")
    for line in THEMES.get(theme, THEMES["dark"]):
        out.append(line + "\n")
    out.append("\n")

    out.append(f'package "{system}" as {_pid(system)} {{\n')
    out.append(f"  actor {USER}\n")
    for c in comps:
        cid = _pid(c["name"])
        tech = c.get("package", c.get("layer", ""))
        shape = "database" if any(k in tech.lower() for k in ("db", "vector", "store", "blob")) else "rectangle"
        out.append(f'  {shape} "{c["name"]}\\n[{tech}]" as {cid}\n')
    out.append("}\n\n")

    for a, b, label in sorted(rels):
        a_id = "User" if a == USER else _pid(a)
        b_id = "User" if b == USER else _pid(b)
        out.append(f"{a_id} --> {b_id} : {label}\n")

    out.append("@enduml\n")
    return "".join(out)


# --- main ---------------------------------------------------------------------
def main():
    ensure_dirs()
    model = load_model()

    # 1) Structurizr
    (C4_DIR / "structurizr.dsl").write_text(to_structurizr(model), encoding="utf-8")

    # 2) Mermaid
    for name, mmd in to_mermaid_sequences(model).items():
        (MM_DIR / f"{name}.mmd").write_text(mmd, encoding="utf-8")

    # 3) Component docs
    for c in iter_components(model):
        (COMP_DIR / f"{c['name']}.md").write_text(component_markdown(c), encoding="utf-8")

    # 4) Import Linter config
    (ARCH_DIR / "importlinter.ini").write_text(to_import_linter(model), encoding="utf-8")

    # 5) Plain PlantUML (dark + light)
    (C4_DIR / "c4_plain_dark.puml").write_text(to_plain_plantuml(model, "dark"), encoding="utf-8")
    (C4_DIR / "c4_plain_light.puml").write_text(to_plain_plantuml(model, "light"), encoding="utf-8")

    # 6) Root docs index
    index_md = [f"# {model.get('system', 'System')} — Architecture\n\n"]
    index_md.append("## Components\n\n")
    for c in model.get("components", []) or []:
        index_md.append(f"- [{c['name']}](./components/{c['name']}.md)\n")
    index_md.append("\n## Diagrams\n\n")
    index_md.append("- [C4 model (Structurizr DSL)](./diagrams/c4/structurizr.dsl)\n")
    for flow in model.get("flows", []) or []:
        nm = flow.get("name")
        index_md.append(f"- {nm} (Mermaid): ./diagrams/mermaid/{nm}.mmd\n")
    (DOCS / "index.md").write_text("".join(index_md), encoding="utf-8")

    print("Generated: Structurizr DSL, Mermaid flows, component docs, importlinter.ini, PlantUML (dark+light)")


if __name__ == "__main__":
    main()
