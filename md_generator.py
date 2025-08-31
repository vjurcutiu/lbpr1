#!/usr/bin/env python3
"""
md2files: Extract code blocks from Markdown and write them to files.

Usage:
  md2files README.md
  md2files docs/*.md --base-dir out --dry-run
  md2files spec.md --lang python --lang ts --overwrite

Rules:
- Only fenced code blocks (``` or ~~~) are processed.
- The first non-empty line inside each block must be a comment with the destination path.
  Examples of acceptable first lines:
    # src/app/main.py
    // web/index.html
    <!-- ui/styles.css -->
    -- db/schema.sql
    ; scripts/setup.sh
    % notes/example.txt
    ' VB/path.bas
    (* src/file.ml *)
    /* src/file.c */
- That path is interpreted relative to --base-dir (default: current directory).
- By default, the tool refuses to write outside --base-dir for safety.
- Use --overwrite to allow overwriting existing files.
- Use --lang to process only specific code block languages (repeatable).
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple, List

FENCE_RE = re.compile(
    r"(?P<fence>```|~~~)"           # opening fence
    r"(?P<info>[^\n]*)\n"           # info string (language, etc.) up to newline
    r"(?P<body>.*?)(?:\n)?"
    r"(?P=fence)\s*",               # matching closing fence
    re.DOTALL
)

# Comment starters and wrappers:
LINE_COMMENT_MARKERS = [
    "#", "//", ";", "--", "%", "'", "!", "REM ", "rem ", "::"  # batch, SQL, Basic, etc.
]
WRAPPED_COMMENT_PATTERNS = [
    (r"^<!--\s*(?P<path>.+?)\s*-->$",),         # HTML
    (r"^/\*\s*(?P<path>.+?)\s*\*/$",),          # C-style
    (r"^\(\*\s*(?P<path>.+?)\s*\*\)$",),        # ML-style
]

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create files from Markdown code blocks whose first line comment holds the path.")
    p.add_argument("inputs", nargs="+", help="Markdown file(s) to parse")
    p.add_argument("--base-dir", default=".", help="Base output directory (default: .)")
    p.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing files")
    p.add_argument("--lang", action="append", default=[], help="Only process blocks whose language matches (repeatable)")
    p.add_argument("--encoding", default="utf-8", help="File encoding for outputs (default: utf-8)")
    p.add_argument("--allow-outside", action="store_true", help="Permit writing outside --base-dir (unsafe)")
    return p.parse_args()

def iter_code_blocks(markdown: str) -> Iterator[Tuple[Optional[str], str, int]]:
    """
    Yield (language, body, start_index) for each fenced block.
    """
    for m in FENCE_RE.finditer(markdown):
        info = (m.group("info") or "").strip()
        lang = None
        if info:
            # language is the first token in info string
            lang = info.split()[0]
        yield (lang, m.group("body"), m.start())

def extract_path_from_first_line(first_line: str) -> Optional[str]:
    """
    Extract a file path from a commented first line.
    Returns the raw path string if recognized, else None.
    """
    line = first_line.strip()

    # Wrapped comment styles
    for (pattern,) in WRAPPED_COMMENT_PATTERNS:
        m = re.match(pattern, line)
        if m:
            return m.group("path").strip()

    # Line comment styles (support `# path`, `// path`, `REM path`, etc.)
    for marker in LINE_COMMENT_MARKERS:
        if line.startswith(marker):
            # After the marker, everything is the path
            return line[len(marker):].strip()

    # Also allow a plain path (no comment) if it LOOKS like a path (has / or \ or a dot and no spaces)
    if ("/" in line or "\\" in line or "." in line) and not line.endswith(":") and not line.startswith("```"):
        # Heuristic: avoid obvious code lines (contains spaces that look like code statements)
        if " " not in line:
            return line.strip()

    return None

def split_first_line(body: str) -> Tuple[str, str]:
    """
    Return (first_non_empty_line, remainder_text) from a code block body.
    If the body is empty or all whitespace, first line is "".
    """
    lines = body.splitlines()
    # find first non-empty line index
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines):
        return ("", "")
    first = lines[idx]
    remainder = "\n".join(lines[idx+1:]) + ("\n" if body.endswith("\n") else "")
    return (first, remainder)

def is_allowed_lang(lang: Optional[str], allowed: List[str]) -> bool:
    if not allowed:
        return True
    if lang is None:
        return False
    # match loosely, e.g., "python", "py", "ts", "typescript"
    aliases = {
        "py": "python",
        "ts": "typescript",
        "js": "javascript",
        "sh": "bash",
        "ps1": "powershell",
        "ps": "powershell",
        "csharp": "cs",
    }
    norm = lang.lower()
    norm = aliases.get(norm, norm)
    canon_allowed = {aliases.get(a.lower(), a.lower()) for a in allowed}
    return norm in canon_allowed

def safe_join(base: Path, rel: str, allow_outside: bool) -> Path:
    target = (base / rel).resolve()
    if not allow_outside:
        base_resolved = base.resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Refusing to write outside base dir: {target} (base: {base_resolved})")
    return target

def process_file(path: Path, args: argparse.Namespace) -> int:
    md = path.read_text(encoding=args.encoding)
    wrote = 0
    for lang, body, _ in iter_code_blocks(md):
        if not is_allowed_lang(lang, args.lang):
            continue
        first, remainder = split_first_line(body)
        if not first:
            continue
        dest = extract_path_from_first_line(first)
        if not dest:
            continue

        out_path = safe_join(Path(args.base_dir), dest, args.allow_outside)
        if out_path.exists() and not args.overwrite:
            print(f"[skip] {out_path} exists (use --overwrite)", file=sys.stderr)
            continue

        if args.dry_run:
            print(f"[dry-run] Would write {out_path} ({len(remainder)} bytes)")
            wrote += 1
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(remainder, encoding=args.encoding)
        print(f"[write] {out_path} ({len(remainder)} bytes)")
        wrote += 1
    return wrote

def main() -> None:
    args = parse_args()
    base = Path(args.base_dir)
    base.mkdir(parents=True, exist_ok=True)

    total = 0
    for pattern in args.inputs:
        for p in sorted(Path().glob(pattern)):
            if p.is_file():
                total += process_file(p, args)
    if total == 0:
        print("No files written (no matching code blocks with path comments found).", file=sys.stderr)

if __name__ == "__main__":
    main()
