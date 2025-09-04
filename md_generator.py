#!/usr/bin/env python3
# ruff: noqa
r"""
md_generator.py
Extract files from:
  1) Hex-stream "filestart" headers:
       66696c657374617274 path/to/file.py
       ... file body until next header ...
  2) Fenced code blocks where the path is indicated by a comment marker line
     near the top (default marker: '*&^file'), with fallback to "first
     non-empty line is a comment containing path".

Safety & UX:
- Paths are sanitized (converts '**init**.py' -> '__init__.py', strips quotes/backticks/invisibles).
- By default, refuses to write outside --base-dir unless --allow-outside is passed.
- On any error for a particular header/block, logs and CONTINUES (does not abort).
- Final summary includes written, skipped, and errored counts.

Usage examples:
  python md_generator.py inputs.md --base-dir out
  python md_generator.py docs/*.md --dry-run --debug
  python md_generator.py spec.md --marker "@file" --marker-scan-lines 999
  python md_generator.py spec.md --lang python --overwrite
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Set

# ---------------------------
# Parsing config / regexes
# ---------------------------

# Robust fenced blocks: allow 3+ backticks/ tildes, up to 3 spaces indent
FENCE_RE = re.compile(
    r"(?:^|\n)"                         # start or newline
    r"(?P<indent>[ \t]{0,3})"           # up to 3 spaces indent
    r"(?P<fence>```+|~~~+)[ \t]*"       # 3+ backticks or tildes
    r"(?P<info>[^\n]*)\n"               # info string (language, etc.)
    r"(?P<body>.*?)(?:\n)"              # body (non-greedy)
    r"(?P=indent)(?P=fence)[ \t]*"      # closing fence with same indent/char/len
    r"(?=\n|$)",                        # followed by newline or end
    re.DOTALL
)

LINE_COMMENT_MARKERS = [
    "#", "//", ";", "--", "%", "'", "!", "REM ", "rem ", "::"
]
WRAPPED_COMMENT_PATTERNS = [
    (r"^<!--\s*(?P<inner>.+?)\s*-->$",),
    (r"^/\*\s*(?P<inner>.+?)\s*\*/$",),
    (r"^\(\*\s*(?P<inner>.+?)\s*\*\)$",),
]

# Hex header for "filestart"
FILESTART_HEX = "66696c657374617274"
HEX_HEADER_RE = re.compile(rf"^[ \t]*{FILESTART_HEX}[ \t]+(?P<path>\S+)[ \t]*$", re.MULTILINE)
HEX_PREFIX_RE = re.compile(rf"^\s*{FILESTART_HEX}\s+(?P<rest>.+)$")

# Lines commonly injected by copy-paste from UIs
NOISE_SINGLE_LINES = {
    "Copy code", "copy code",
    "python", "py",
    "ts", "tsx",
    "js", "javascript",
    "bash", "sh",
    "html", "css",
    "json", "toml", "yaml", "yml",
    "sql", "go", "rust", "cpp", "c", "cs", "java", "kotlin", "swift",
    "powershell", "ps1",
}

INVALID_WIN_CHARS = set('<>:"|?*')  # path component invalids on Windows


# ---------------------------
# CLI
# ---------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract files from hex-stream or fenced code blocks.")
    p.add_argument("inputs", nargs="+", help="Input files (supports glob patterns)")
    p.add_argument("--base-dir", default=".", help="Base output directory (default: .)")
    p.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files")
    p.add_argument("--dry-run", action="store_true", help="Show actions without writing files")
    p.add_argument("--encoding", default="utf-8", help="File encoding for outputs (default: utf-8)")
    p.add_argument("--allow-outside", action="store_true", help="Permit writing outside --base-dir (unsafe)")
    p.add_argument("--lang", action="append", default=[], help="Only process fenced blocks of these languages (repeatable)")
    p.add_argument("--marker", default="*&^file", help="Comment marker token searched near top of fenced blocks (default: '*&^file')")
    p.add_argument("--marker-scan-lines", type=int, default=10, help="Top N lines to scan for the marker (default: 10)")
    p.add_argument("--debug", action="store_true", help="Verbose debug output to stderr")
    return p.parse_args()


# ---------------------------
# Path & text sanitization
# ---------------------------

def _strip_invisibles(s: str) -> str:
    # remove common zero-width / BOM / word-joiner chars
    return (
        s.replace("\u200b", "")
         .replace("\u200c", "")
         .replace("\u200d", "")
         .replace("\u2060", "")
         .replace("\ufeff", "")
         .strip()
    )

def sanitize_dest_path(dest: str, fix_md_emphasis: bool = True) -> str:
    """
    Make a path extracted from markdown/UI safe:
    - strip surrounding quotes/backticks/invisible characters
    - convert **name** to __name__ (markdown bold gone literal)
    - unescape '\\_' -> '_'
    - validate components for Windows-illegal chars
    """
    s = dest.strip().strip('`"\'')
    s = _strip_invisibles(s)

    # Reject obvious non-path junk (single bullets/dashes)
    if s in {"-", "–", "—", "*"}:
        raise ValueError(f"Rejected non-path token {dest!r}")

    if fix_md_emphasis:
        # "**init**.py" -> "__init__.py", and "**dir**/file" -> "__dir__/file"
        s = re.sub(r"\*\*([A-Za-z0-9_.-]+)\*\*", r"__\1__", s)

    # Undo markdown-style escaped underscores inside names (warning-free)
    s = s.replace("\\_", "_")

    # Normalize to forward slashes for internal handling
    s = s.replace("\\", "/")

    # Remove empty elements, '.' current-dir elements
    parts = [p for p in s.split("/") if p not in ("", ".")]

    # Validate components
    for p in parts:
        bad = INVALID_WIN_CHARS.intersection(p)
        if bad:
            raise ValueError(
                f"Invalid character(s) {''.join(sorted(bad))!r} in path component {p!r} derived from {dest!r}."
            )

    # Reconstruct
    cleaned = "/".join(parts)
    if not cleaned:
        raise ValueError(f"Empty/invalid destination path derived from {dest!r}.")
    return cleaned


def _strip_win_longprefix(p: Path) -> Path:
    s = str(p)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    return Path(s)

def _is_within_base(base: Path, target: Path) -> bool:
    """
    Reliable, prefix-insensitive containment check:
    try target.relative_to(base) after stripping any Windows long-path prefix.
    """
    b = _strip_win_longprefix(base.resolve())
    t = _strip_win_longprefix(target.resolve())
    try:
        t.relative_to(b)
        return True
    except Exception:
        return False

def safe_join(base: Path, rel: str, allow_outside: bool) -> Path:
    target = (base / rel).resolve()
    if not allow_outside and not _is_within_base(base, target):
        raise ValueError(f"Refusing to write outside base dir: {target} (base: {base.resolve()})")
    return target


# ---------------------------
# Fenced block helpers
# ---------------------------

def iter_code_blocks(markdown: str):
    for m in FENCE_RE.finditer(markdown):
        info = (m.group("info") or "").strip()
        lang = info.split()[0] if info else None
        yield (lang, m.group("body"), m.start())

def _strip_wrapped_comment(line: str) -> Optional[str]:
    for (pattern,) in WRAPPED_COMMENT_PATTERNS:
        m = re.match(pattern, line.strip())
        if m:
            return m.group("inner").strip()
    return None

def _strip_line_comment_prefix(line: str) -> Optional[str]:
    s = line.lstrip()
    for mk in LINE_COMMENT_MARKERS:
        if s.startswith(mk):
            return s[len(mk):].strip()
    return None

def _looks_like_comment(line: str) -> bool:
    return _strip_line_comment_prefix(line) is not None or _strip_wrapped_comment(line) is not None

def _extract_after_marker(s: str, marker: str) -> Optional[str]:
    idx = s.find(marker)
    if idx < 0:
        return None
    tail = s[idx + len(marker):].strip()
    if tail.startswith(":") or tail.startswith("="):
        tail = tail[1:].strip()
    if (tail.startswith('"') and tail.endswith('"')) or (tail.startswith("'") and tail.endswith("'")):
        tail = tail[1:-1].strip()
    return tail or None

def _strip_embedded_hex_prefix(line: str) -> str:
    """If a line starts with the filestart hex and a space, drop it and return the rest."""
    m = HEX_PREFIX_RE.match(line)
    return m.group("rest") if m else line

def extract_path_from_marker(lines: List[str], marker: str, max_scan: int) -> Optional[Tuple[str, int]]:
    scan_limit = min(max_scan, len(lines))
    for i in range(scan_limit):
        raw = lines[i]
        # Try wrapped comments
        inner = _strip_wrapped_comment(raw)
        if inner is not None:
            p = _extract_after_marker(inner, marker)
            if p:
                return (_strip_embedded_hex_prefix(p), i)
        # Try line comments
        tail = _strip_line_comment_prefix(raw)
        if tail is not None:
            p = _extract_after_marker(tail, marker)
            if p:
                return (_strip_embedded_hex_prefix(p), i)
        # Stop early once real code starts
        if raw.strip() and not _looks_like_comment(raw):
            break
    return None

def split_first_line(body: str) -> Tuple[str, str]:
    lines = body.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return ("", "")
    first = lines[i]
    rest = "\n".join(lines[i+1:]) + ("\n" if body.endswith("\n") else "")
    return (first, rest)

def extract_path_from_first_line(first_line: str) -> Optional[str]:
    line = _strip_embedded_hex_prefix(first_line.strip())
    for (pattern,) in WRAPPED_COMMENT_PATTERNS:
        m = re.match(pattern, line)
        if m:
            return m.group("inner").strip()
    for mk in LINE_COMMENT_MARKERS:
        if line.startswith(mk):
            return line[len(mk):].strip()
    # last resort: accept *reasonable* bare relative paths (no spaces, has dot/slash)
    if re.match(r"^(?![\\/])(?=.*[./\\]).+[A-Za-z0-9_\-./\\]$", line) and " " not in line:
        return line
    return None


# ---------------------------
# Hex-stream mode
# ---------------------------

def _clean_stream_block(text: str) -> str:
    lines = text.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if s in NOISE_SINGLE_LINES:
            continue
        if s in ("```", "~~~"):
            continue
        out.append(ln)
    # trim surrounding blank lines (nice-to-have)
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()
    return ("\n".join(out) + ("\n" if text.endswith("\n") else ""))

def process_hex_stream(md: str, base_dir: Path, allow_outside: bool, overwrite: bool,
                       dry_run: bool, encoding: str, debug: bool,
                       already_written: Set[Path]) -> Tuple[int, int, int]:
    wrote = skipped = errored = 0
    matches = list(HEX_HEADER_RE.finditer(md))
    for idx, m in enumerate(matches):
        dest_raw = m.group("path")
        start = m.end()
        end = matches[idx+1].start() if idx + 1 < len(matches) else len(md)
        body_raw = md[start:end]
        body = _clean_stream_block(body_raw)

        try:
            dest = sanitize_dest_path(dest_raw)
            out_path = safe_join(base_dir, dest, allow_outside)

            if out_path in already_written:
                if debug:
                    print(f"[skip-dup] {out_path}", file=sys.stderr)
                skipped += 1
                continue

            if out_path.exists() and not overwrite:
                print(f"[skip] {out_path} exists (use --overwrite)", file=sys.stderr)
                skipped += 1
                continue

            if dry_run:
                print(f"[dry-run] Would write {out_path} ({len(body)} bytes)")
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(body, encoding=encoding)
                print(f"[write] {out_path} ({len(body)} bytes)")
            wrote += 1
            already_written.add(out_path)

        except Exception as e:
            errored += 1
            print(f"[error] hex {dest_raw!r}: {e}", file=sys.stderr)
            if debug:
                print(f"[debug] offending block preview:\n{body[:300]}\n---", file=sys.stderr)

    if debug:
        print(f"[hex-mode] headers={len(matches)} wrote={wrote} skipped={skipped} errors={errored}", file=sys.stderr)
    return wrote, skipped, errored


# ---------------------------
# Fenced mode
# ---------------------------

def is_allowed_lang(lang: Optional[str], allowed: List[str]) -> bool:
    if not allowed:
        return True
    if lang is None:
        return False
    aliases = {
        "py": "python",
        "ts": "typescript",
        "js": "javascript",
        "sh": "bash",
        "ps1": "powershell",
        "ps": "powershell",
        "csharp": "cs",
    }
    norm = aliases.get(lang.lower(), lang.lower())
    canon_allowed = {aliases.get(a.lower(), a.lower()) for a in allowed}
    return norm in canon_allowed

def process_fenced(md: str, base_dir: Path, allow_outside: bool, overwrite: bool,
                   dry_run: bool, encoding: str, marker: str, marker_scan_lines: int,
                   lang_filter: List[str], debug: bool, already_written: Set[Path]) -> Tuple[int, int, int]:
    wrote = skipped = errored = 0
    for lang, body, _ in iter_code_blocks(md):
        if not is_allowed_lang(lang, lang_filter):
            continue
        lines = body.splitlines()
        dest_raw = None
        remainder = body
        try:
            marker_hit = extract_path_from_marker(lines, marker, marker_scan_lines)
            if marker_hit:
                dest_raw, marker_idx = marker_hit
                out_lines = lines[:marker_idx] + lines[marker_idx+1:]
                remainder = "\n".join(out_lines) + ("\n" if body.endswith("\n") else "")
            else:
                first, remainder = split_first_line(body)
                dest_raw = extract_path_from_first_line(first)

            if not dest_raw:
                continue  # silent skip if fenced block doesn't declare a path

            # Normalize away embedded hex header if present
            dest_raw = _strip_embedded_hex_prefix(dest_raw)

            dest = sanitize_dest_path(dest_raw)
            out_path = safe_join(base_dir, dest, allow_outside)

            if out_path in already_written:
                if debug:
                    print(f"[skip-dup] {out_path}", file=sys.stderr)
                skipped += 1
                continue
            if out_path.exists() and not overwrite:
                print(f"[skip] {out_path} exists (use --overwrite)", file=sys.stderr)
                skipped += 1
                continue

            if dry_run:
                print(f"[dry-run] Would write {out_path} ({len(remainder)} bytes)")
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(remainder, encoding=encoding)
                print(f"[write] {out_path} ({len(remainder)} bytes)")
            wrote += 1
            already_written.add(out_path)

        except Exception as e:
            errored += 1
            blk_preview = remainder[:300]
            print(f"[error] fenced lang={lang!r} path={dest_raw!r}: {e}", file=sys.stderr)
            if debug:
                print(f"[debug] block preview:\n{blk_preview}\n---", file=sys.stderr)

    if debug:
        print(f"[fenced-mode] wrote={wrote} skipped={skipped} errors={errored}", file=sys.stderr)
    return wrote, skipped, errored


# ---------------------------
# Main
# ---------------------------

def main() -> None:
    args = parse_args()
    base = Path(args.base_dir)
    base.mkdir(parents=True, exist_ok=True)

    total_wrote = total_skipped = total_errors = 0

    for pattern in args.inputs:
        for p in sorted(Path().glob(pattern)):
            if not p.is_file():
                continue
            try:
                md = p.read_text(encoding=args.encoding)
            except Exception as e:
                total_errors += 1
                print(f"[error] reading {p}: {e}", file=sys.stderr)
                continue

            already_written: Set[Path] = set()

            w, s, e = process_hex_stream(
                md, base, args.allow_outside, args.overwrite,
                args.dry_run, args.encoding, args.debug, already_written
            )
            total_wrote += w; total_skipped += s; total_errors += e

            w, s, e = process_fenced(
                md, base, args.allow_outside, args.overwrite, args.dry_run,
                args.encoding, args.marker, args.marker_scan_lines,
                args.lang, args.debug, already_written
            )
            total_wrote += w; total_skipped += s; total_errors += e

    if total_wrote == 0 and total_skipped == 0 and total_errors == 0:
        print("No files written (no matching markers found).", file=sys.stderr)

    print(f"[summary] wrote={total_wrote} skipped={total_skipped} errors={total_errors}")

if __name__ == "__main__":
    main()
