#!/usr/bin/env python3
"""
Lightweight placeholder-language lint for the Mintlify docs repo.

Goals:
- Prevent "placeholder" phrases from creeping into published docs.
- Keep the rules intentionally small and explicit.

Usage:
  python3 scripts/docs_placeholder_lint.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

DIR_EXCLUDES = {"snippets", "yaml-files", "internal"}


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]


PATTERNS: list[Pattern] = [
    Pattern("coming_soon", re.compile(r"\bcoming soon\b", re.IGNORECASE)),
    Pattern("under_construction", re.compile(r"\bunder construction\b", re.IGNORECASE)),
    Pattern("todo", re.compile(r"\bTODO\b")),
    Pattern("tbd", re.compile(r"\bTBD\b")),
    Pattern("lorem_ipsum", re.compile(r"\blorem\b|\bipsum\b", re.IGNORECASE)),
    Pattern("tablestakes_typo", re.compile(r"\btablestakes\b", re.IGNORECASE)),
]


def is_excluded(rel: Path) -> bool:
    if any(part.startswith(".") for part in rel.parts):
        return True
    if rel.parts and rel.parts[0] in DIR_EXCLUDES:
        return True
    return False


def iter_doc_files() -> Iterable[Path]:
    for ext in ("*.mdx", "*.md"):
        for path in REPO_ROOT.rglob(ext):
            rel = path.relative_to(REPO_ROOT)
            if is_excluded(rel):
                continue
            yield path


def main() -> int:
    matches: list[str] = []
    for path in iter_doc_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            for pattern in PATTERNS:
                if pattern.regex.search(line):
                    rel = path.relative_to(REPO_ROOT)
                    matches.append(f"{rel}:{i}: {pattern.name}")

    if matches:
        print(f"[ERROR] Placeholder language found in {len(matches)} location(s):")
        for m in matches[:100]:
            print(f"  - {m}")
        if len(matches) > 100:
            print(f"  ... and {len(matches) - 100} more")
        return 1

    print("[OK] Placeholder lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

