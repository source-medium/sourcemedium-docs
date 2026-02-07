#!/usr/bin/env python3
"""
Sync SourceMedium docs into Ragie with strict partition scoping.

Behavior:
- Discovers published docs from docs.json
- Normalizes MDX/Markdown into retrieval text
- Upserts via external_id in a target partition
- Deletes stale docs in that partition
- Polls ingestion status for changed docs

Usage examples:
  python3 scripts/ragie_sync.py --partition shared_docs
  python3 scripts/ragie_sync.py --partition tenant_acme --doc-ref onboarding/getting-started/intro-to-sm --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_JSON = REPO_ROOT / "docs.json"
ENV_FILE = REPO_ROOT / ".env"

MANAGED_METADATA_KEYS = {
    "source",
    "repo",
    "docs_ref",
    "url_path",
    "url_full",
    "title",
    "description",
    "content_hash",
    "commit_sha",
    "visibility",
    "tenant_id",
    "taxonomy_version",
    "doc_domain",
    "doc_subdomain",
    "content_type",
    "primary_surface",
    "surfaces",
    "topic_tags",
    "frontmatter_tags",
    "taxonomy_source",
}

TERMINAL_FAILURE_STATUSES = {"failed"}

SURFACE_ENUM = [
    "query_snippets",
    "looker_studio",
    "bigquery",
    "managed_warehouse",
    "dashboard",
    "mta",
    "configuration_sheet",
    "general",
]

CONTENT_TYPE_ENUM = [
    "query_snippet_library",
    "data_table_reference",
    "template_resource",
    "dashboard_module_reference",
    "managed_bi_guide",
    "managed_warehouse_guide",
    "faq",
    "core_concept",
    "analytics_tool_guide",
    "onboarding_guide",
    "integration_guide",
    "mta_guide",
    "general_doc",
]

DEFAULT_ENTITY_INSTRUCTION_PROMPT = (
    "Extract analytics support entities from this SourceMedium documentation page. "
    "Return a JSON object with: "
    "surfaces (subset of allowed surfaces), "
    "keywords (short lowercase topic tags), "
    "table_names (BigQuery tables like obt_orders), "
    "column_names (notable field names), "
    "dashboard_modules (dashboard/module names), "
    "integration_platforms (platform/vendor names). "
    "Use empty arrays when unavailable."
)


def build_partition_metadata_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "source": {
                "type": "string",
                "description": "Source marker for managed docs in this repository.",
            },
            "repo": {
                "type": "string",
                "description": "Repository identifier for managed docs.",
            },
            "docs_ref": {
                "type": "string",
                "description": "Canonical docs route/path without extension.",
            },
            "title": {
                "type": "string",
                "description": "Document title from frontmatter.",
            },
            "description": {
                "type": "string",
                "description": "Short document summary from frontmatter.",
            },
            "visibility": {
                "type": "string",
                "description": "Whether the doc is in a shared or tenant partition.",
                "enum": ["shared", "tenant"],
            },
            "tenant_id": {
                "type": "string",
                "description": "Tenant identifier for tenant partitions.",
            },
            "content_type": {
                "type": "string",
                "description": "High-level document class derived from docs path.",
                "enum": CONTENT_TYPE_ENUM,
            },
            "primary_surface": {
                "type": "string",
                "description": "Primary analytics surface for the doc.",
                "enum": SURFACE_ENUM,
            },
            "surfaces": {
                "type": "array",
                "description": "All relevant analytics surfaces for the doc.",
                "items": {"type": "string", "enum": SURFACE_ENUM},
                "uniqueItems": True,
            },
            "topic_tags": {
                "type": "array",
                "description": "Normalized topic tags used for retrieval filtering.",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "frontmatter_tags": {
                "type": "array",
                "description": "Optional frontmatter tags from markdown.",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
        },
    }


def build_entity_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "surfaces": {
                "type": "array",
                "items": {"type": "string", "enum": SURFACE_ENUM},
                "uniqueItems": True,
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "table_names": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "column_names": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "dashboard_modules": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "integration_platforms": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
        },
        "required": [
            "surfaces",
            "keywords",
            "table_names",
            "column_names",
            "dashboard_modules",
            "integration_platforms",
        ],
    }


def default_partition_description(partition: str) -> str:
    if partition == "shared_docs":
        return (
            "SourceMedium public documentation covering onboarding, integrations, "
            "data transformations, managed BI/Looker Studio dashboards, BigQuery table "
            "references, SQL query snippets, and help-center FAQs."
        )
    tenant_id = partition.removeprefix("tenant_")
    return (
        f"SourceMedium tenant documentation partition for '{tenant_id}'. Contains tenant-"
        "scoped docs and the same core product documentation categories used for support retrieval."
    )


def default_entity_instruction_name(partition: str) -> str:
    return f"sourcemedium-doc-entities-v1-{partition}"


class SyncError(RuntimeError):
    """Raised for sync/runtime failures."""


@dataclass(frozen=True)
class LocalDoc:
    ref: str
    path: Path
    name: str
    external_id: str
    content: str
    content_hash: str
    metadata: dict[str, Any]


def log(message: str) -> None:
    print(message)


def load_local_env(path: Path) -> None:
    """Load .env into process env for local runs (without overriding existing env)."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def sanitize_partition(partition: str) -> str:
    value = partition.strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]+", value):
        raise SyncError(
            f"Invalid partition '{partition}'. Partition must match ^[a-z0-9_-]+$."
        )
    return value


def extract_page_refs(obj: Any, refs: set[str]) -> None:
    if isinstance(obj, str):
        if obj.startswith("http") or obj.startswith("#"):
            return
        refs.add(obj.lstrip("/"))
        return

    if isinstance(obj, list):
        for item in obj:
            extract_page_refs(item, refs)
        return

    if isinstance(obj, dict):
        for key in ("tabs", "pages", "navigation", "groups"):
            if key in obj:
                extract_page_refs(obj[key], refs)


def load_docs_refs() -> list[str]:
    if not DOCS_JSON.exists():
        raise SyncError(f"docs.json not found at {DOCS_JSON}")

    raw = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    refs: set[str] = set()
    extract_page_refs(raw, refs)
    return sorted(refs)


def resolve_ref_path(ref: str) -> Path | None:
    candidates = [
        REPO_ROOT / f"{ref}.mdx",
        REPO_ROOT / f"{ref}.md",
        REPO_ROOT / ref / "index.mdx",
        REPO_ROOT / ref / "index.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def extract_tenant_slug_from_ref(ref: str) -> str | None:
    normalized = ref.lstrip("/")
    if not normalized.startswith("tenants/"):
        return None

    parts = normalized.split("/")
    if len(parts) < 2:
        return None

    tenant_slug = parts[1].strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]+", tenant_slug):
        return None
    return tenant_slug


def tenant_slug_from_partition(partition: str) -> str | None:
    if not partition.startswith("tenant_"):
        return None
    tenant_slug = partition.removeprefix("tenant_").strip().lower()
    if not tenant_slug:
        return None
    if not re.fullmatch(r"[a-z0-9_-]+", tenant_slug):
        raise SyncError(
            f"Invalid tenant partition '{partition}'. Expected tenant_<tenant_slug> with slug matching ^[a-z0-9_-]+$."
        )
    return tenant_slug


def discover_tenant_refs(tenant_slug: str) -> list[str]:
    refs: set[str] = set()

    top_level_candidates = [
        REPO_ROOT / "tenants" / f"{tenant_slug}.mdx",
        REPO_ROOT / "tenants" / f"{tenant_slug}.md",
    ]
    for path in top_level_candidates:
        if path.exists():
            rel = path.relative_to(REPO_ROOT).with_suffix("")
            refs.add(str(rel).replace(os.sep, "/"))

    tenant_dir = REPO_ROOT / "tenants" / tenant_slug
    if tenant_dir.exists():
        for path in tenant_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".mdx"}:
                continue
            rel = path.relative_to(REPO_ROOT).with_suffix("")
            refs.add(str(rel).replace(os.sep, "/"))

    return sorted(refs)


def scope_refs_for_partition(
    *,
    refs: list[str],
    partition: str,
) -> list[str]:
    tenant_slug = tenant_slug_from_partition(partition)

    if tenant_slug:
        tenant_refs = discover_tenant_refs(tenant_slug)
        if not tenant_refs:
            log(f"[WARN] No tenant docs found under /tenants for tenant slug '{tenant_slug}'")
        return tenant_refs

    # Shared/non-tenant partitions must never include /tenants docs.
    scoped = [ref for ref in refs if extract_tenant_slug_from_ref(ref) is None]
    excluded = len(refs) - len(scoped)
    if excluded:
        log(f"[INFO] Excluded tenant docs from partition '{partition}': {excluded}")
    return scoped


def _strip_wrapping_quotes(value: str) -> str:
    raw = value.strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1].strip()
    return raw


def _parse_inline_tags(raw_value: str) -> list[str]:
    value = _strip_wrapping_quotes(raw_value)
    if not value:
        return []

    if value.startswith("[") and value.endswith("]"):
        inside = value[1:-1].strip()
        if not inside:
            return []
        return [
            _strip_wrapping_quotes(item).strip()
            for item in inside.split(",")
            if _strip_wrapping_quotes(item).strip()
        ]

    if "," in value:
        return [
            _strip_wrapping_quotes(item).strip()
            for item in value.split(",")
            if _strip_wrapping_quotes(item).strip()
        ]

    return [value]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text

    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", text, flags=re.S)
    if not match:
        return {}, text

    fm_raw = match.group(1)
    body = text[match.end() :]

    fm: dict[str, Any] = {}
    lines = fm_raw.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            idx += 1
            continue

        key = m.group(1).strip()
        value = m.group(2).strip()

        if key == "tags":
            tags = _parse_inline_tags(value)
            j = idx + 1
            while j < len(lines):
                tag_match = re.match(r"^\s*-\s+(.+)$", lines[j])
                if not tag_match:
                    break
                tag_value = _strip_wrapping_quotes(tag_match.group(1)).strip()
                if tag_value:
                    tags.append(tag_value)
                j += 1
            fm[key] = tags
            idx = j
            continue

        fm[key] = _strip_wrapping_quotes(value)
        idx += 1

    return fm, body


def _strip_inline_tags(text: str) -> str:
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", text, flags=re.S)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    text = re.sub(r"\{\s*[A-Za-z_][^{}\n]*\}", "", text)
    return text


def _collapse_spaces(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_doc_text(raw_text: str, fallback_title: str) -> tuple[str, dict[str, Any]]:
    frontmatter, body = parse_frontmatter(raw_text)

    title = frontmatter.get("title") or fallback_title
    description = frontmatter.get("description") or ""

    body = body.replace("\r\n", "\n").replace("\r", "\n")

    segments = re.split(r"(```[\s\S]*?```)", body)

    callouts = {
        "Info": "Info",
        "Tip": "Tip",
        "Note": "Note",
        "Warning": "Warning",
    }

    processed: list[str] = []
    for segment in segments:
        if not segment:
            continue
        if segment.startswith("```"):
            processed.append(segment)
            continue

        part = segment
        part = re.sub(r"(?m)^\s*(import|export)\s+.+$", "", part)

        for tag, label in callouts.items():
            pattern = re.compile(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", flags=re.I)

            def repl(match: re.Match[str], label: str = label) -> str:
                inner = _strip_inline_tags(match.group(1))
                inner = _collapse_spaces(inner)
                return f"{label}: {inner}" if inner else label

            part = pattern.sub(repl, part)

        part = _strip_inline_tags(part)
        processed.append(part)

    normalized_body = "".join(processed)
    normalized_body = _collapse_spaces(normalized_body)

    preamble_parts = [f"# {title}"]
    if description:
        preamble_parts.append(description)

    full_text = "\n\n".join(preamble_parts + [normalized_body]).strip() + "\n"

    normalized_fm = {
        "title": title,
        "description": description,
        "tags": frontmatter.get("tags", []),
    }
    return full_text, normalized_fm


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_tag_value(tag: str) -> str:
    return re.sub(r"\s+", "_", tag.strip().lower())


def derive_taxonomy(
    *,
    ref: str,
    title: str,
    description: str,
    frontmatter_tags: list[str] | None = None,
) -> dict[str, Any]:
    parts = ref.split("/")
    doc_domain = parts[0] if parts else "unknown"
    doc_subdomain = "/".join(parts[:2]) if len(parts) >= 2 else doc_domain

    ref_lower = ref.lower()
    text = f"{ref} {title} {description}".lower()

    content_type = "general_doc"
    if ref_lower == "data-activation/template-resources/sql-query-library":
        content_type = "query_snippet_library"
    elif ref_lower.startswith("data-activation/data-tables/"):
        content_type = "data_table_reference"
    elif ref_lower.startswith("data-activation/template-resources/"):
        content_type = "template_resource"
    elif ref_lower.startswith("data-activation/managed-bi-v1/modules/"):
        content_type = "dashboard_module_reference"
    elif ref_lower.startswith("data-activation/managed-bi-v1/"):
        content_type = "managed_bi_guide"
    elif ref_lower.startswith("data-activation/managed-data-warehouse/"):
        content_type = "managed_warehouse_guide"
    elif ref_lower.startswith("help-center/faq/"):
        content_type = "faq"
    elif ref_lower.startswith("help-center/core-concepts/"):
        content_type = "core_concept"
    elif ref_lower.startswith("onboarding/analytics-tools/"):
        content_type = "analytics_tool_guide"
    elif ref_lower.startswith("onboarding/getting-started/"):
        content_type = "onboarding_guide"
    elif ref_lower.startswith("data-inputs/platform-integration-instructions/"):
        content_type = "integration_guide"
    elif ref_lower.startswith("mta/"):
        content_type = "mta_guide"

    surfaces: set[str] = set()
    if ref_lower.startswith("data-activation/managed-bi-v1/modules/"):
        # Managed BI modules are dashboard-facing docs and should be routed as such.
        surfaces.update({"dashboard", "looker_studio"})
    elif ref_lower.startswith("data-activation/managed-bi-v1/"):
        surfaces.add("dashboard")
    if "looker studio" in text or "looker-studio" in text or "looker" in text:
        surfaces.add("looker_studio")
    if "bigquery" in text or "sql" in text or ref_lower.startswith("data-activation/data-tables/"):
        surfaces.add("bigquery")
    if "dashboard" in text:
        surfaces.add("dashboard")
    if "warehouse" in text or ref_lower.startswith("data-activation/managed-data-warehouse/"):
        surfaces.add("managed_warehouse")
    if ref_lower.startswith("mta/"):
        surfaces.add("mta")
    if "configuration-sheet" in ref_lower:
        surfaces.add("configuration_sheet")

    if not surfaces:
        surfaces.add("general")

    primary_surface_priority = [
        "query_snippets",
        "looker_studio",
        "bigquery",
        "managed_warehouse",
        "dashboard",
        "mta",
        "configuration_sheet",
        "general",
    ]
    primary_surface = "general"
    for candidate in primary_surface_priority:
        if candidate in surfaces:
            primary_surface = candidate
            break

    frontmatter_tags = frontmatter_tags or []
    normalized_frontmatter_tags = sorted(
        {_normalize_tag_value(tag) for tag in frontmatter_tags if str(tag).strip()}
    )

    topic_tags: set[str] = {
        f"domain:{doc_domain}",
        f"subdomain:{doc_subdomain}",
        f"content_type:{content_type}",
    }
    topic_tags.update(f"surface:{surface}" for surface in surfaces)
    topic_tags.update(normalized_frontmatter_tags)

    if ref_lower == "data-activation/template-resources/sql-query-library":
        topic_tags.update({"query_snippets", "sql_examples", "analytics_queries"})
        surfaces.add("query_snippets")
        primary_surface = "query_snippets"

    topic_tags.add(f"surface:{primary_surface}")

    if "template" in ref_lower:
        topic_tags.add("templates")
    if content_type == "faq":
        topic_tags.add("support")
    if content_type.endswith("_guide"):
        topic_tags.add("how_to")

    return {
        "taxonomy_version": "v1",
        "doc_domain": doc_domain,
        "doc_subdomain": doc_subdomain,
        "content_type": content_type,
        "primary_surface": primary_surface,
        "surfaces": sorted(surfaces),
        "topic_tags": sorted(topic_tags),
        "frontmatter_tags": normalized_frontmatter_tags,
        "taxonomy_source": "derived+frontmatter",
    }


class RagieClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: int,
        max_retries: int,
        retry_base_delay: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        partition: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if query:
            clean_query = {k: v for k, v in query.items() if v is not None}
            query_str = urlencode(clean_query)
            url = f"{self.base_url}{path}?{query_str}" if query_str else f"{self.base_url}{path}"
        else:
            url = f"{self.base_url}{path}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if partition:
            headers["partition"] = partition

        payload: bytes | None = None
        if json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url=url, data=payload, method=method, headers=headers)

        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(req, timeout=self.timeout) as response:
                    raw = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        if not raw:
                            return {}
                        return json.loads(raw.decode("utf-8"))
                    return raw
            except HTTPError as err:
                status = err.code
                raw = err.read().decode("utf-8", errors="ignore")
                detail = raw
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict) and parsed.get("detail"):
                        detail = str(parsed["detail"])
                except json.JSONDecodeError:
                    pass

                if status in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    sleep_for = self.retry_base_delay * (2**attempt)
                    time.sleep(sleep_for)
                    continue

                raise SyncError(f"Ragie API error {status} for {method} {path}: {detail}") from err
            except URLError as err:
                if attempt < self.max_retries:
                    sleep_for = self.retry_base_delay * (2**attempt)
                    time.sleep(sleep_for)
                    continue
                raise SyncError(f"Network error for {method} {path}: {err}") from err

        raise SyncError(f"Exhausted retries for {method} {path}")

    def list_documents(self, partition: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            response = self._request(
                "GET",
                "/documents",
                query={"page_size": 100, "cursor": cursor},
                partition=partition,
            )
            page_docs = response.get("documents", [])
            if not isinstance(page_docs, list):
                raise SyncError("Unexpected /documents response shape: missing documents[]")
            docs.extend(page_docs)

            pagination = response.get("pagination", {}) or {}
            cursor = pagination.get("next_cursor")
            if not cursor:
                break

        return docs

    def create_document_raw(
        self,
        *,
        partition: str,
        name: str,
        external_id: str,
        metadata: dict[str, Any],
        data: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/documents/raw",
            json_body={
                "name": name,
                "external_id": external_id,
                "partition": partition,
                "metadata": metadata,
                "data": data,
            },
        )

    def update_document_raw(self, *, partition: str, document_id: str, data: str) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/documents/{document_id}/raw",
            partition=partition,
            json_body={"data": data},
        )

    def patch_document_metadata(
        self,
        *,
        partition: str,
        document_id: str,
        metadata_patch: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/documents/{document_id}/metadata",
            partition=partition,
            json_body={"metadata": metadata_patch, "async": False},
        )

    def get_document(self, *, partition: str, document_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/documents/{document_id}",
            partition=partition,
        )

    def delete_document(self, *, partition: str, document_id: str, async_delete: bool) -> dict[str, Any]:
        return self._request(
            "DELETE",
            f"/documents/{document_id}",
            partition=partition,
            query={"async": str(async_delete).lower()},
        )

    def list_partitions(self) -> list[dict[str, Any]]:
        partitions: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            response = self._request(
                "GET",
                "/partitions",
                query={"page_size": 100, "cursor": cursor},
            )
            page = response.get("partitions", [])
            if not isinstance(page, list):
                raise SyncError("Unexpected /partitions response shape: missing partitions[]")
            partitions.extend(page)
            pagination = response.get("pagination", {}) or {}
            cursor = pagination.get("next_cursor")
            if not cursor:
                break
        return partitions

    def create_partition(
        self,
        *,
        name: str,
        description: str | None,
        metadata_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        if metadata_schema is not None:
            payload["metadata_schema"] = metadata_schema
        return self._request("POST", "/partitions", json_body=payload)

    def get_partition(self, *, partition_id: str) -> dict[str, Any]:
        return self._request("GET", f"/partitions/{partition_id}")

    def update_partition(
        self,
        *,
        partition_id: str,
        context_aware: bool | None = None,
        description: str | None = None,
        metadata_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if context_aware is not None:
            payload["context_aware"] = context_aware
        if description is not None:
            payload["description"] = description
        if metadata_schema is not None:
            payload["metadata_schema"] = metadata_schema
        if not payload:
            return self.get_partition(partition_id=partition_id)
        return self._request("PATCH", f"/partitions/{partition_id}", json_body=payload)

    def list_instructions(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/instructions")
        if not isinstance(response, list):
            raise SyncError("Unexpected /instructions response shape: expected list")
        return response

    def create_instruction(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/instructions", json_body=payload)

    def update_instruction_active(self, *, instruction_id: str, active: bool) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/instructions/{instruction_id}",
            json_body={"active": active},
        )

    def list_entities_by_document(
        self,
        *,
        partition: str,
        document_id: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/documents/{document_id}/entities",
            partition=partition,
            query={"cursor": cursor, "page_size": page_size},
        )


def build_local_docs(
    *,
    refs: list[str],
    partition: str,
    docs_base_url: str,
    repo_name: str,
    source: str,
    commit_sha: str,
) -> list[LocalDoc]:
    docs: list[LocalDoc] = []

    visibility = "shared" if partition == "shared_docs" else "tenant"
    tenant_id = partition.removeprefix("tenant_") if partition.startswith("tenant_") else partition

    for ref in refs:
        path = resolve_ref_path(ref)
        if path is None:
            log(f"[WARN] Missing file for docs ref '{ref}', skipping")
            continue

        rel_path = path.relative_to(REPO_ROOT)
        if rel_path.parts[0] in {"snippets", "specs"}:
            continue

        raw_text = path.read_text(encoding="utf-8", errors="ignore")
        fallback_title = ref.rsplit("/", 1)[-1].replace("-", " ").strip().title() or ref
        content, fm = normalize_doc_text(raw_text, fallback_title)

        content_hash = sha256_text(content)

        url_path = "/" + ref.lstrip("/")
        url_full = docs_base_url.rstrip("/") + url_path

        taxonomy = derive_taxonomy(
            ref=ref,
            title=fm.get("title", fallback_title),
            description=fm.get("description", ""),
            frontmatter_tags=fm.get("tags", []),
        )

        metadata: dict[str, Any] = {
            "source": source,
            "repo": repo_name,
            "docs_ref": ref,
            "url_path": url_path,
            "url_full": url_full,
            "title": fm.get("title", fallback_title),
            "description": fm.get("description", ""),
            "content_hash": content_hash,
            "visibility": visibility,
            "tenant_id": tenant_id,
        }
        metadata.update(taxonomy)
        if commit_sha:
            metadata["commit_sha"] = commit_sha

        external_id = f"repo:{repo_name}|partition:{partition}|ref:{ref}"
        name = ref

        docs.append(
            LocalDoc(
                ref=ref,
                path=path,
                name=name,
                external_id=external_id,
                content=content,
                content_hash=content_hash,
                metadata=metadata,
            )
        )

    return docs


def compare_metadata_patch(remote_metadata: dict[str, Any], desired_metadata: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}

    for key in MANAGED_METADATA_KEYS:
        remote_present = key in remote_metadata
        desired_present = key in desired_metadata

        if desired_present and remote_metadata.get(key) != desired_metadata.get(key):
            patch[key] = desired_metadata[key]
        elif remote_present and not desired_present:
            patch[key] = None

    return patch


def is_managed_remote_doc(doc: dict[str, Any], *, source: str, repo_name: str) -> bool:
    metadata = doc.get("metadata") or {}
    return metadata.get("source") == source and metadata.get("repo") == repo_name


def pick_latest_doc(docs: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    def updated_at_key(doc: dict[str, Any]) -> str:
        return str(doc.get("updated_at") or "")

    ordered = sorted(docs, key=updated_at_key, reverse=True)
    return ordered[0], ordered[1:]


def poll_changed_documents(
    *,
    client: RagieClient,
    partition: str,
    document_ids: list[str],
    timeout_seconds: int,
    interval_seconds: float,
    allow_indexed: bool,
) -> None:
    if not document_ids:
        return

    success_statuses = {"ready"}
    if allow_indexed:
        success_statuses.update({"indexed", "summary_indexed", "keyword_indexed"})

    pending = set(document_ids)
    failures: list[tuple[str, list[str]]] = []
    deadline = time.time() + timeout_seconds

    while pending and time.time() < deadline:
        for document_id in list(pending):
            doc = client.get_document(partition=partition, document_id=document_id)
            status = str(doc.get("status") or "").strip().lower()
            if status in success_statuses:
                pending.remove(document_id)
                continue
            if status in TERMINAL_FAILURE_STATUSES:
                pending.remove(document_id)
                errors = doc.get("errors") or []
                if not isinstance(errors, list):
                    errors = [str(errors)]
                failures.append((document_id, [str(e) for e in errors]))

        if pending:
            time.sleep(interval_seconds)

    if pending:
        waiting = ", ".join(sorted(pending))
        raise SyncError(
            f"Timed out waiting for Ragie documents to finish indexing in partition '{partition}': {waiting}"
        )

    if failures:
        details = "; ".join(
            f"{doc_id}: {', '.join(errs) if errs else 'unknown error'}" for doc_id, errs in failures
        )
        raise SyncError(f"One or more Ragie documents failed indexing: {details}")


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":"), ensure_ascii=True) == json.dumps(
        right,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def ensure_partition_configuration(
    *,
    client: RagieClient,
    partition: str,
    description: str,
    metadata_schema: dict[str, Any],
    dry_run: bool,
) -> None:
    partitions = client.list_partitions()
    exists = any(str(item.get("name") or "") == partition for item in partitions)

    if not exists:
        if dry_run:
            log(f"[DRY-RUN] CREATE_PARTITION {partition}")
        else:
            client.create_partition(
                name=partition,
                description=description,
                metadata_schema=metadata_schema,
            )
            log(f"[PARTITION_CREATE] {partition}")

    if dry_run and not exists:
        log(f"[DRY-RUN] PATCH_PARTITION {partition} keys=[context_aware,description,metadata_schema]")
        return

    detail = client.get_partition(partition_id=partition)
    patch: dict[str, Any] = {}

    if detail.get("context_aware") is not True:
        patch["context_aware"] = True
    if description and str(detail.get("description") or "") != description:
        patch["description"] = description
    if not _json_equal(detail.get("metadata_schema"), metadata_schema):
        patch["metadata_schema"] = metadata_schema

    if not patch:
        log(f"[INFO] Partition '{partition}' already configured for context-aware retrieval")
        return

    if dry_run:
        keys = ",".join(sorted(patch.keys()))
        log(f"[DRY-RUN] PATCH_PARTITION {partition} keys=[{keys}]")
        return

    # Ragie currently rejects context_aware + description in the same PATCH payload.
    # Apply in two steps when both are needed.
    non_context_patch = {
        key: patch[key]
        for key in ("description", "metadata_schema")
        if key in patch
    }
    if non_context_patch:
        client.update_partition(
            partition_id=partition,
            description=non_context_patch.get("description"),
            metadata_schema=non_context_patch.get("metadata_schema"),
        )
        keys = ",".join(sorted(non_context_patch.keys()))
        log(f"[PARTITION_PATCH] {partition} keys=[{keys}]")

    if "context_aware" in patch:
        client.update_partition(
            partition_id=partition,
            context_aware=bool(patch["context_aware"]),
        )
        log(f"[PARTITION_PATCH] {partition} keys=[context_aware]")


def ensure_entity_instruction(
    *,
    client: RagieClient,
    partition: str,
    source: str,
    repo_name: str,
    instruction_name: str,
    scope: str,
    dry_run: bool,
) -> bool:
    expected_payload: dict[str, Any] = {
        "name": instruction_name,
        "active": True,
        "scope": scope,
        "prompt": DEFAULT_ENTITY_INSTRUCTION_PROMPT,
        "entity_schema": build_entity_schema(),
        "filter": {
            "source": {"$eq": source},
            "repo": {"$eq": repo_name},
        },
        "partition": partition,
    }

    instructions = client.list_instructions()
    matches = [inst for inst in instructions if str(inst.get("name") or "") == instruction_name]

    if not matches:
        if dry_run:
            log(f"[DRY-RUN] CREATE_INSTRUCTION {instruction_name} partition={partition}")
            return False
        created = client.create_instruction(payload=expected_payload)
        log(f"[INSTRUCTION_CREATE] {instruction_name} id={created.get('id')}")
        return True

    instruction = matches[0]
    if len(matches) > 1:
        log(f"[WARN] Multiple instructions found for name '{instruction_name}', using newest by API order")

    instruction_id = str(instruction.get("id") or "")
    if not bool(instruction.get("active")):
        if dry_run:
            log(f"[DRY-RUN] ACTIVATE_INSTRUCTION {instruction_name} id={instruction_id}")
        elif instruction_id:
            client.update_instruction_active(instruction_id=instruction_id, active=True)
            log(f"[INSTRUCTION_ACTIVATE] {instruction_name} id={instruction_id}")

    drift_fields: list[str] = []
    if str(instruction.get("partition") or "") != partition:
        drift_fields.append("partition")
    if str(instruction.get("scope") or "") != scope:
        drift_fields.append("scope")
    if str(instruction.get("prompt") or "") != DEFAULT_ENTITY_INSTRUCTION_PROMPT:
        drift_fields.append("prompt")
    if not _json_equal(instruction.get("entity_schema"), expected_payload["entity_schema"]):
        drift_fields.append("entity_schema")
    if not _json_equal(instruction.get("filter"), expected_payload["filter"]):
        drift_fields.append("filter")

    if drift_fields:
        joined = ",".join(sorted(drift_fields))
        log(
            "[WARN] Instruction config drift detected for "
            f"'{instruction_name}' (fields: {joined}). Ragie only supports active-state updates; "
            "delete/recreate instruction to apply config changes."
        )
    else:
        log(f"[INFO] Instruction '{instruction_name}' already configured")

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync SourceMedium docs into Ragie")
    parser.add_argument("--partition", required=True, help="Ragie partition (e.g. shared_docs, tenant_acme)")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Sync mode (currently both modes use full diff-based reconciliation)",
    )
    parser.add_argument(
        "--doc-ref",
        action="append",
        default=[],
        help="Optional docs ref to sync. Repeatable for multiple refs.",
    )
    parser.add_argument("--source", default="sourcemedium-docs", help="Managed metadata source marker")
    parser.add_argument("--repo-name", default="sourcemedium-docs", help="Repo name for metadata/external_id")
    parser.add_argument("--docs-base-url", default="https://docs.sourcemedium.com", help="Base URL for url_full metadata")
    parser.add_argument("--base-url", default="https://api.ragie.ai", help="Ragie API base URL")
    parser.add_argument("--commit-sha", default="", help="Commit SHA to stamp in metadata")
    parser.add_argument(
        "--ensure-partition-context-aware",
        action="store_true",
        help="Ensure partition has context-aware retrieval enabled with description + metadata schema",
    )
    parser.add_argument(
        "--partition-description",
        default="",
        help="Optional partition description override used with --ensure-partition-context-aware",
    )
    parser.add_argument(
        "--ensure-entity-instruction",
        action="store_true",
        help="Ensure a partition-scoped entity extraction instruction exists",
    )
    parser.add_argument(
        "--entity-instruction-name",
        default="",
        help="Optional instruction name override (default: sourcemedium-doc-entities-v1-<partition>)",
    )
    parser.add_argument(
        "--entity-instruction-scope",
        choices=["document", "chunk"],
        default="document",
        help="Instruction scope for entity extraction",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute and print actions without writing to Ragie")
    parser.add_argument("--allow-indexed", action="store_true", help="Treat indexed/summary_indexed/keyword_indexed as success")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")
    parser.add_argument("--max-retries", type=int, default=4, help="HTTP retry attempts for retryable errors")
    parser.add_argument("--retry-base-delay", type=float, default=0.5, help="Exponential backoff base delay in seconds")
    parser.add_argument("--poll-timeout", type=int, default=600, help="Polling timeout in seconds")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds")
    parser.add_argument(
        "--skip-remote",
        action="store_true",
        help="Skip Ragie API reads/writes (useful for local content-shaping validation)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    load_local_env(ENV_FILE)

    partition = sanitize_partition(args.partition)

    commit_sha = args.commit_sha.strip() or os.environ.get("GITHUB_SHA", "").strip()

    refs = load_docs_refs()
    refs = scope_refs_for_partition(refs=refs, partition=partition)
    requested_doc_refs = [r.lstrip("/") for r in args.doc_ref if str(r).strip()]
    partial_sync = bool(requested_doc_refs)
    if requested_doc_refs:
        wanted = set(requested_doc_refs)
        refs = [r for r in refs if r in wanted]
        missing = sorted(wanted - set(refs))
        if missing:
            raise SyncError(
                f"doc_ref(s) not available for partition '{partition}': {', '.join(missing)}"
            )

    local_docs = build_local_docs(
        refs=refs,
        partition=partition,
        docs_base_url=args.docs_base_url,
        repo_name=args.repo_name,
        source=args.source,
        commit_sha=commit_sha,
    )

    if not local_docs:
        raise SyncError("No local docs discovered to sync")

    local_by_external = {doc.external_id: doc for doc in local_docs}
    local_refs = {doc.ref for doc in local_docs}

    log(f"[INFO] Local docs discovered: {len(local_docs)}")

    if args.skip_remote:
        log("[INFO] --skip-remote enabled, ending after local discovery")
        return 0

    api_key = os.environ.get("RAGIE_API_KEY", "").strip()
    if not api_key:
        raise SyncError("RAGIE_API_KEY is not set (env or .env)")

    client = RagieClient(
        api_key=api_key,
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_base_delay=args.retry_base_delay,
    )

    created_instruction = False
    if args.ensure_partition_context_aware:
        desired_description = args.partition_description.strip() or default_partition_description(partition)
        ensure_partition_configuration(
            client=client,
            partition=partition,
            description=desired_description,
            metadata_schema=build_partition_metadata_schema(),
            dry_run=args.dry_run,
        )

    if args.ensure_entity_instruction:
        instruction_name = args.entity_instruction_name.strip() or default_entity_instruction_name(partition)
        created_instruction = ensure_entity_instruction(
            client=client,
            partition=partition,
            source=args.source,
            repo_name=args.repo_name,
            instruction_name=instruction_name,
            scope=args.entity_instruction_scope,
            dry_run=args.dry_run,
        )

    remote_docs_all = client.list_documents(partition=partition)
    managed_remote_docs = [
        doc for doc in remote_docs_all if is_managed_remote_doc(doc, source=args.source, repo_name=args.repo_name)
    ]

    log(
        f"[INFO] Remote docs in partition '{partition}': total={len(remote_docs_all)} managed={len(managed_remote_docs)}"
    )

    grouped_by_external: dict[str, list[dict[str, Any]]] = {}
    remote_without_external: list[dict[str, Any]] = []
    for doc in managed_remote_docs:
        ext = str(doc.get("external_id") or "").strip()
        if not ext:
            remote_without_external.append(doc)
            continue
        grouped_by_external.setdefault(ext, []).append(doc)

    remote_by_external: dict[str, dict[str, Any]] = {}
    duplicate_docs: list[dict[str, Any]] = []

    for external_id, docs in grouped_by_external.items():
        keep, dups = pick_latest_doc(docs)
        remote_by_external[external_id] = keep
        duplicate_docs.extend(dups)

    create_docs: list[LocalDoc] = []
    update_raw_docs: list[tuple[LocalDoc, dict[str, Any]]] = []
    patch_metadata_docs: list[tuple[LocalDoc, dict[str, Any], dict[str, Any]]] = []

    for external_id, local in local_by_external.items():
        remote = remote_by_external.get(external_id)
        if remote is None:
            create_docs.append(local)
            continue

        remote_metadata = remote.get("metadata") or {}
        if not isinstance(remote_metadata, dict):
            remote_metadata = {}

        metadata_patch = compare_metadata_patch(remote_metadata, local.metadata)
        remote_hash = str(remote_metadata.get("content_hash") or "")
        needs_raw_update = remote_hash != local.content_hash

        if needs_raw_update:
            update_raw_docs.append((local, remote))

        if metadata_patch:
            patch_metadata_docs.append((local, remote, metadata_patch))

    stale_docs: list[dict[str, Any]] = []
    stale_no_external_docs: list[dict[str, Any]] = []
    skipped_no_external = 0

    if not partial_sync:
        stale_external_ids = sorted(set(remote_by_external.keys()) - set(local_by_external.keys()))
        stale_docs = [remote_by_external[eid] for eid in stale_external_ids]

        for doc in remote_without_external:
            metadata = doc.get("metadata") or {}
            docs_ref = str(metadata.get("docs_ref") or "").strip()
            if docs_ref and docs_ref not in local_refs:
                stale_no_external_docs.append(doc)
            else:
                skipped_no_external += 1
    else:
        # In partial mode, only clean duplicates for targeted external_ids.
        duplicate_docs = [
            doc for doc in duplicate_docs if str(doc.get("external_id") or "") in set(local_by_external.keys())
        ]

    log(
        "[INFO] Plan: "
        f"create={len(create_docs)} "
        f"update_raw={len(update_raw_docs)} "
        f"patch_metadata={len(patch_metadata_docs)} "
        f"delete_stale={len(stale_docs)} "
        f"delete_duplicates={len(duplicate_docs)} "
        f"delete_stale_no_external={len(stale_no_external_docs)}"
    )
    if partial_sync:
        log("[INFO] Partial sync mode enabled via --doc-ref (stale deletion disabled)")
    if skipped_no_external:
        log(f"[WARN] Managed docs without external_id kept (no safe delete signal): {skipped_no_external}")

    if args.dry_run:
        for doc in create_docs[:20]:
            log(f"[DRY-RUN] CREATE {doc.ref}")
        for local, remote in update_raw_docs[:20]:
            log(f"[DRY-RUN] UPDATE_RAW {local.ref} doc_id={remote.get('id')}")
        for local, remote, metadata_patch in patch_metadata_docs[:20]:
            patch_keys = ",".join(sorted(metadata_patch.keys()))
            log(f"[DRY-RUN] PATCH_METADATA {local.ref} doc_id={remote.get('id')} keys=[{patch_keys}]")
        for doc in stale_docs[:20]:
            log(f"[DRY-RUN] DELETE_STALE external_id={doc.get('external_id')} doc_id={doc.get('id')}")
        for doc in duplicate_docs[:20]:
            log(f"[DRY-RUN] DELETE_DUPLICATE external_id={doc.get('external_id')} doc_id={doc.get('id')}")
        for doc in stale_no_external_docs[:20]:
            md = doc.get("metadata") or {}
            log(f"[DRY-RUN] DELETE_STALE_NO_EXTERNAL docs_ref={md.get('docs_ref')} doc_id={doc.get('id')}")
        log("[INFO] Dry-run complete")
        return 0

    changed_document_ids: list[str] = []

    for local in create_docs:
        response = client.create_document_raw(
            partition=partition,
            name=local.name,
            external_id=local.external_id,
            metadata=local.metadata,
            data=local.content,
        )
        doc_id = str(response.get("id") or "")
        if not doc_id:
            raise SyncError(f"Create returned no document id for {local.ref}")
        changed_document_ids.append(doc_id)
        log(f"[CREATE] {local.ref} -> {doc_id}")

    for local, remote in update_raw_docs:
        doc_id = str(remote.get("id") or "")
        if not doc_id:
            raise SyncError(f"Remote document missing id for update: {local.ref}")
        client.update_document_raw(partition=partition, document_id=doc_id, data=local.content)
        changed_document_ids.append(doc_id)
        log(f"[UPDATE_RAW] {local.ref} -> {doc_id}")

    for local, remote, metadata_patch in patch_metadata_docs:
        doc_id = str(remote.get("id") or "")
        if not doc_id:
            raise SyncError(f"Remote document missing id for metadata patch: {local.ref}")
        client.patch_document_metadata(
            partition=partition,
            document_id=doc_id,
            metadata_patch=metadata_patch,
        )
        log(f"[PATCH_METADATA] {local.ref} -> {doc_id}")

    for doc in stale_docs:
        doc_id = str(doc.get("id") or "")
        if not doc_id:
            continue
        client.delete_document(partition=partition, document_id=doc_id, async_delete=True)
        log(f"[DELETE_STALE] doc_id={doc_id}")

    for doc in duplicate_docs:
        doc_id = str(doc.get("id") or "")
        if not doc_id:
            continue
        client.delete_document(partition=partition, document_id=doc_id, async_delete=True)
        log(f"[DELETE_DUPLICATE] doc_id={doc_id}")

    for doc in stale_no_external_docs:
        doc_id = str(doc.get("id") or "")
        if not doc_id:
            continue
        client.delete_document(partition=partition, document_id=doc_id, async_delete=True)
        log(f"[DELETE_STALE_NO_EXTERNAL] doc_id={doc_id}")

    changed_document_ids = sorted(set(changed_document_ids))

    poll_changed_documents(
        client=client,
        partition=partition,
        document_ids=changed_document_ids,
        timeout_seconds=args.poll_timeout,
        interval_seconds=args.poll_interval,
        allow_indexed=args.allow_indexed,
    )

    log(
        f"[OK] Sync complete for partition '{partition}': "
        f"created={len(create_docs)} updated={len(update_raw_docs)} "
        f"patched={len(patch_metadata_docs)} deleted={len(stale_docs) + len(duplicate_docs) + len(stale_no_external_docs)}"
    )
    if created_instruction and not changed_document_ids:
        log(
            "[WARN] Entity instruction was created but no documents changed in this run. "
            "Run a full sync to backfill extracted entities on existing docs."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as err:
        log(f"[ERROR] {err}")
        raise SystemExit(1)
