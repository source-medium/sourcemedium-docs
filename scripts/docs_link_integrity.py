#!/usr/bin/env python3
"""
Validate internal documentation links and local image references.

Checks:
1) Internal links to doc routes (e.g. /help-center/...) resolve to an existing page.
2) Local image links under /images/... resolve to an existing file.

Usage:
  python3 scripts/docs_link_integrity.py
  python3 scripts/docs_link_integrity.py path/to/file1.mdx path/to/file2.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_EXTENSIONS = {".mdx", ".md"}
EXCLUDED_TOP_LEVEL_DIRS = {"snippets", "yaml-files", "internal", "tenants"}
EXCLUDED_TOP_LEVEL_FILES = {"AGENTS.md", "CLAUDE.md", "README.md", "skill.md"}

# Markdown and common MDX attribute links.
MD_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ATTR_LINK_PATTERN = re.compile(r"""(?:href|to|src)\s*=\s*["']([^"']+)["']""")


def is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    if any(part.startswith(".") for part in rel.parts):
        return True
    if len(rel.parts) == 1 and rel.name in EXCLUDED_TOP_LEVEL_FILES:
        return True
    return bool(rel.parts and rel.parts[0] in EXCLUDED_TOP_LEVEL_DIRS)


def iter_doc_files() -> Iterable[Path]:
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in DOC_EXTENSIONS:
            continue
        if is_excluded(path):
            continue
        yield path


def load_frontmatter_route(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return None
    _, _, rest = text.partition("---")
    frontmatter, _, _ = rest.partition("---")
    route_match = re.search(r"""^route:\s*(.+?)\s*$""", frontmatter, flags=re.M)
    if not route_match:
        return None
    raw = route_match.group(1).strip().strip('"').strip("'")
    if not raw.startswith("/"):
        return None
    return normalize_route(raw)


def normalize_route(route: str) -> str:
    if route != "/" and route.endswith("/"):
        return route[:-1]
    return route


def build_route_set() -> set[str]:
    routes: set[str] = set()
    for path in REPO_ROOT.rglob("*.mdx"):
        if is_excluded(path):
            continue
        rel_no_ext = path.relative_to(REPO_ROOT).with_suffix("").as_posix()
        routes.add(normalize_route(f"/{rel_no_ext}"))
        if path.name == "index.mdx":
            routes.add(normalize_route(f"/{path.parent.relative_to(REPO_ROOT).as_posix()}"))
        custom_route = load_frontmatter_route(path)
        if custom_route:
            routes.add(custom_route)

    # Root is valid if index.mdx exists.
    if (REPO_ROOT / "index.mdx").exists():
        routes.add("/")

    # Redirect sources are also valid user-facing targets.
    docs_json = REPO_ROOT / "docs.json"
    if docs_json.exists():
        try:
            import json

            data = json.loads(docs_json.read_text(encoding="utf-8"))
            for item in data.get("redirects", []):
                source = item.get("source")
                if isinstance(source, str) and source.startswith("/"):
                    routes.add(normalize_route(source))
        except Exception:
            pass
    return routes


def collect_targets(path: Path) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line_no, line in enumerate(lines, start=1):
        for pattern in (MD_LINK_PATTERN, ATTR_LINK_PATTERN):
            for match in pattern.finditer(line):
                targets.append((line_no, match.group(1).strip()))
    return targets


def should_skip_target(target: str) -> bool:
    if not target:
        return True
    if target.startswith("#"):
        return True
    if "{" in target or "}" in target:
        # Ignore template-driven values.
        return True
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        # External schemes like https:, mailto:, tel:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional .md/.mdx files to check. Defaults to all docs files.",
    )
    args = parser.parse_args()

    if args.files:
        files = []
        for raw in args.files:
            path = (REPO_ROOT / raw).resolve() if not raw.startswith("/") else Path(raw).resolve()
            if not path.exists() or not path.is_file():
                continue
            if path.suffix.lower() not in DOC_EXTENSIONS:
                continue
            if is_excluded(path):
                continue
            files.append(path)
    else:
        files = list(iter_doc_files())

    routes = build_route_set()
    missing_routes: list[str] = []
    missing_images: list[str] = []

    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        for line_no, target in collect_targets(path):
            if should_skip_target(target):
                continue

            base_target = target.split("#", 1)[0].split("?", 1)[0]
            if not base_target:
                continue
            if not base_target.startswith("/"):
                # Non-root relative links are not validated by this checker.
                continue

            if base_target.startswith("/snippets/"):
                continue

            if base_target.startswith("/images/"):
                image_path = REPO_ROOT / base_target.lstrip("/")
                if not image_path.exists():
                    missing_images.append(f"{rel}:{line_no} -> {base_target}")
                continue

            normalized = normalize_route(base_target)
            if normalized not in routes:
                missing_routes.append(f"{rel}:{line_no} -> {base_target}")

    if missing_routes or missing_images:
        if missing_routes:
            print(f"[ERROR] Missing internal route targets: {len(missing_routes)}")
            for item in missing_routes[:200]:
                print(f"  - {item}")
            if len(missing_routes) > 200:
                print(f"  ... and {len(missing_routes) - 200} more")
        if missing_images:
            print(f"[ERROR] Missing local image targets: {len(missing_images)}")
            for item in missing_images[:200]:
                print(f"  - {item}")
            if len(missing_images) > 200:
                print(f"  ... and {len(missing_images) - 200} more")
        return 1

    print(f"[OK] Link integrity check passed ({len(files)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
