#!/usr/bin/env python3
"""
Docs inventory checks for the Mintlify site.

Checks:
1) Metadata: every page MDX has non-empty title/description/icon in frontmatter
2) Orphans: every page MDX is referenced in docs.json navigation (with allowlisted exceptions)

Usage:
  python3 scripts/docs_inventory.py

Exit codes:
  0 = OK
  1 = issues found
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_JSON = REPO_ROOT / "docs.json"

PAGE_DIR_EXCLUDES = {"snippets", "yaml-files"}
ALLOW_ORPHAN_PATTERNS = [
    r"/hidden-",  # hidden utility pages
    r"template",  # authoring templates
]


@dataclass(frozen=True)
class Frontmatter:
    title: str | None
    description: str | None
    icon: str | None


def is_excluded_path(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if path.parts and path.parts[0] in PAGE_DIR_EXCLUDES:
        return True
    return False


def iter_page_mdx_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*.mdx"):
        rel = path.relative_to(REPO_ROOT)
        if is_excluded_path(rel):
            continue
        yield path


def mdx_ref_from_path(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return str(rel).replace("\\", "/")


def extract_page_refs_from_docs_json(obj: Any, refs: set[str]) -> None:
    """
    Extract docs.json navigation references (paths without .mdx).

    Important: only traverse the navigation structure to avoid accidentally
    collecting arbitrary strings (titles, descriptions, etc.).
    """
    if isinstance(obj, str):
        if obj.startswith("http") or obj.startswith("#"):
            return
        refs.add(obj.lstrip("/"))
        return

    if isinstance(obj, list):
        for item in obj:
            extract_page_refs_from_docs_json(item, refs)
        return

    if isinstance(obj, dict):
        for key in ("tabs", "pages", "navigation", "groups"):
            if key in obj:
                extract_page_refs_from_docs_json(obj[key], refs)


def load_docs_json_refs() -> set[str]:
    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    refs: set[str] = set()
    extract_page_refs_from_docs_json(data, refs)
    return refs


def parse_frontmatter(text: str) -> Frontmatter | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    fm = parts[1]

    def get(key: str) -> str | None:
        m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", fm, flags=re.M)
        if not m:
            return None
        raw = m.group(1).strip()
        # strip quotes
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1].strip()
        return raw or None

    return Frontmatter(title=get("title"), description=get("description"), icon=get("icon"))


def is_allowed_orphan(ref: str) -> bool:
    # allow internal pages to live off-nav
    if ref.startswith("internal/"):
        return True
    for pat in ALLOW_ORPHAN_PATTERNS:
        if re.search(pat, ref, flags=re.IGNORECASE):
            return True
    return False


def main() -> int:
    if not DOCS_JSON.exists():
        print(f"[ERROR] docs.json not found at {DOCS_JSON}")
        return 1

    docs_refs = load_docs_json_refs()
    page_files = list(iter_page_mdx_files())
    page_refs = {mdx_ref_from_path(p) for p in page_files}

    # Metadata check
    metadata_issues: list[str] = []
    for p in page_files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        fm = parse_frontmatter(text)
        if fm is None:
            metadata_issues.append(f"{p.relative_to(REPO_ROOT)}: missing/invalid frontmatter")
            continue
        if not fm.title:
            metadata_issues.append(f"{p.relative_to(REPO_ROOT)}: missing title")
        if not fm.description:
            metadata_issues.append(f"{p.relative_to(REPO_ROOT)}: missing description")
        if not fm.icon:
            metadata_issues.append(f"{p.relative_to(REPO_ROOT)}: missing icon")

    # Orphans check
    orphan_refs = sorted(r for r in (page_refs - docs_refs) if not is_allowed_orphan(r))
    ignored_orphans = sorted(r for r in (page_refs - docs_refs) if is_allowed_orphan(r))

    had_issues = False

    if metadata_issues:
        had_issues = True
        print(f"[ERROR] Missing metadata in {len(metadata_issues)} page(s):")
        for line in metadata_issues[:50]:
            print(f"  - {line}")
        if len(metadata_issues) > 50:
            print(f"  ... and {len(metadata_issues) - 50} more")

    if orphan_refs:
        had_issues = True
        print(f"[ERROR] Orphan pages (not in docs.json): {len(orphan_refs)}")
        for r in orphan_refs[:50]:
            print(f"  - {r}")
        if len(orphan_refs) > 50:
            print(f"  ... and {len(orphan_refs) - 50} more")

    if ignored_orphans:
        print(f"[INFO] Ignored orphans (allowed): {len(ignored_orphans)}")
        for r in ignored_orphans[:20]:
            print(f"  - {r}")
        if len(ignored_orphans) > 20:
            print(f"  ... and {len(ignored_orphans) - 20} more")

    if not had_issues:
        print("[OK] Docs inventory checks passed")
    return 1 if had_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

