#!/usr/bin/env python3
import argparse, re, sys
from pathlib import Path
from typing import Optional, Tuple, List

# --- Fenced-block support (kept from earlier versions) ---
FENCE_RE = re.compile(
    r"(?:^|\n)"
    r"(?P<indent>[ \t]{0,3})"
    r"(?P<fence>```+|~~~+)[ \t]*"
    r"(?P<info>[^\n]*)\n"
    r"(?P<body>.*?)(?:\n)"
    r"(?P=indent)(?P=fence)[ \t]*"
    r"(?=\n|$)", re.DOTALL
)

LINE_COMMENT_MARKERS = ["#","//",";","--","%","'","!","REM ","rem ","::"]
WRAPPED_COMMENT_PATTERNS = [
    (r"^<!--\s*(?P<inner>.+?)\s*-->$",),
    (r"^/\*\s*(?P<inner>.+?)\s*\*/$",),
    (r"^\(\*\s*(?P<inner>.+?)\s*\*\)$",),
]

def parse_args():
    p = argparse.ArgumentParser(description="Extract files from markdown/text via markers or fenced blocks.")
    p.add_argument("inputs", nargs="+", help="Input files (supports glob)")
    p.add_argument("--base-dir", default=".", help="Output base directory")
    p.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files")
    p.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--allow-outside", action="store_true", help="Permit writing outside base dir (unsafe)")
    p.add_argument("--lang", action="append", default=[], help="Only process these fenced languages")
    p.add_argument("--marker", default="*&^file", help="Comment marker inside fenced blocks (default: *&^file)")
    p.add_argument("--marker-scan-lines", type=int, default=10, help="Top N lines to scan for the comment marker")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()

def safe_join(base: Path, rel: str, allow_outside: bool) -> Path:
    target = (base / rel).resolve()
    if not allow_outside:
        base_resolved = base.resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            raise ValueError(f"Refusing to write outside base dir: {target} (base: {base_resolved})")
    return target

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
    if idx < 0: return None
    tail = s[idx+len(marker):].strip()
    if tail.startswith(":") or tail.startswith("="): tail = tail[1:].strip()
    if (tail.startswith('"') and tail.endswith('"')) or (tail.startswith("'") and tail.endswith("'")):
        tail = tail[1:-1].strip()
    return tail or None

def extract_path_from_marker(lines: List[str], marker: str, max_scan: int) -> Optional[Tuple[str,int]]:
    scan_limit = min(max_scan, len(lines))
    for i in range(scan_limit):
        raw = lines[i]
        inner = _strip_wrapped_comment(raw)
        if inner is not None:
            p = _extract_after_marker(inner, marker)
            if p: return (p, i)
        tail = _strip_line_comment_prefix(raw)
        if tail is not None:
            p = _extract_after_marker(tail, marker)
            if p: return (p, i)
        if raw.strip() and not _looks_like_comment(raw):
            break
    return None

def split_first_line(body: str) -> Tuple[str,str]:
    lines = body.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "": i += 1
    if i >= len(lines): return ("","")
    first = lines[i]
    rest = "\n".join(lines[i+1:]) + ("\n" if body.endswith("\n") else "")
    return (first, rest)

def extract_path_from_first_line(first_line: str) -> Optional[str]:
    line = first_line.strip()
    for (pattern,) in WRAPPED_COMMENT_PATTERNS:
        m = re.match(pattern, line)
        if m: return m.group("inner").strip()
    for mk in LINE_COMMENT_MARKERS:
        if line.startswith(mk): return line[len(mk):].strip()
    if ("/" in line or "\\" in line or "." in line) and " " not in line and not line.endswith(":"):
        return line.strip()
    return None

# --- NEW: “filestart” hex-stream mode ---
FILESTART_HEX = "66696c657374617274"  # "filestart" in hex
HEX_HEADER_RE = re.compile(rf"^[ \t]*{FILESTART_HEX}[ \t]+(?P<path>\S+)[ \t]*$", re.MULTILINE)

NOISE_SINGLE_LINES = {
    "Copy code", "copy code",
    "python","ts","tsx","js","javascript","bash","sh","html","css","json","toml","yaml","yml","sql","go","rust","cpp","c","java","kotlin","swift","powershell","ps1",
}

def _clean_stream_block(text: str) -> str:
    lines = text.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if s in NOISE_SINGLE_LINES: 
            continue
        if s in ("```","~~~"):       # stray fences
            continue
        out.append(ln)
    # trim leading/trailing blank lines
    while out and out[0].strip() == "": out.pop(0)
    while out and out[-1].strip() == "": out.pop()
    return ("\n".join(out) + ("\n" if text.endswith("\n") else ""))

def process_hex_stream(md: str, base_dir: Path, allow_outside: bool, overwrite: bool, dry_run: bool, encoding: str, debug: bool, already_written: set) -> int:
    wrote = 0
    matches = list(HEX_HEADER_RE.finditer(md))
    for idx, m in enumerate(matches):
        dest = m.group("path")
        start = m.end()
        end = matches[idx+1].start() if idx+1 < len(matches) else len(md)
        body_raw = md[start:end]
        body = _clean_stream_block(body_raw)

        out_path = safe_join(base_dir, dest, allow_outside)
        if out_path in already_written:
            if debug: print(f"[skip-dup] {out_path}", file=sys.stderr)
            continue
        if out_path.exists() and not overwrite:
            print(f"[skip] {out_path} exists (use --overwrite)", file=sys.stderr)
            continue
        if dry_run:
            print(f"[dry-run] Would write {out_path} ({len(body)} bytes)")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(body, encoding=encoding)
            print(f"[write] {out_path} ({len(body)} bytes)")
        wrote += 1
        already_written.add(out_path)
    if debug:
        print(f"[hex-mode] found {len(matches)} header(s), wrote {wrote}", file=sys.stderr)
    return wrote

# --- main processors ---
def is_allowed_lang(lang: Optional[str], allowed: List[str]) -> bool:
    if not allowed: return True
    if lang is None: return False
    aliases = {"py":"python","ts":"typescript","js":"javascript","sh":"bash","ps1":"powershell","ps":"powershell","csharp":"cs"}
    norm = aliases.get(lang.lower(), lang.lower())
    canon_allowed = {aliases.get(a.lower(), a.lower()) for a in allowed}
    return norm in canon_allowed

def process_fenced(md: str, base_dir: Path, allow_outside: bool, overwrite: bool, dry_run: bool, encoding: str, marker: str, marker_scan_lines: int, lang_filter: List[str], debug: bool, already_written: set) -> int:
    wrote = 0
    for lang, body, _ in iter_code_blocks(md):
        if not is_allowed_lang(lang, lang_filter):
            continue
        lines = body.splitlines()
        marker_hit = extract_path_from_marker(lines, marker, marker_scan_lines)
        if marker_hit:
            dest, marker_idx = marker_hit
            out_lines = lines[:marker_idx] + lines[marker_idx+1:]
            remainder = "\n".join(out_lines) + ("\n" if body.endswith("\n") else "")
        else:
            first, remainder = split_first_line(body)
            dest = extract_path_from_first_line(first)
        if not dest:
            continue

        out_path = safe_join(base_dir, dest, allow_outside)
        if out_path in already_written:
            if debug: print(f"[skip-dup] {out_path}", file=sys.stderr)
            continue
        if out_path.exists() and not overwrite:
            print(f"[skip] {out_path} exists (use --overwrite)", file=sys.stderr)
            continue
        if dry_run:
            print(f"[dry-run] Would write {out_path} ({len(remainder)} bytes)")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(remainder, encoding=encoding)
            print(f"[write] {out_path} ({len(remainder)} bytes)")
        wrote += 1
        already_written.add(out_path)
    if debug:
        print(f"[fenced-mode] wrote {wrote}", file=sys.stderr)
    return wrote

def main():
    args = parse_args()
    base = Path(args.base_dir); base.mkdir(parents=True, exist_ok=True)
    total = 0
    for pattern in args.inputs:
        for p in sorted(Path().glob(pattern)):
            if not p.is_file(): continue
            md = p.read_text(encoding=args.encoding)
            already_written = set()

            # 1) Try hex-stream mode (your case)
            total += process_hex_stream(md, base, args.allow_outside, args.overwrite, args.dry_run, args.encoding, args.debug, already_written)
            # 2) Also allow fenced blocks in the same file (optional)
            total += process_fenced(md, base, args.allow_outside, args.overwrite, args.dry_run, args.encoding, args.marker, args.marker_scan_lines, args.lang, args.debug, already_written)

    if total == 0:
        print("No files written (no matching markers found).", file=sys.stderr)

if __name__ == "__main__":
    main()
