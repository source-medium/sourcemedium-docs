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
}

TERMINAL_FAILURE_STATUSES = {"failed"}


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


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text

    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", text, flags=re.S)
    if not match:
        return {}, text

    fm_raw = match.group(1)
    body = text[match.end() :]

    fm: dict[str, str] = {}
    for line in fm_raw.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1).strip()
        value = m.group(2).strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1].strip()
        fm[key] = value

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


def normalize_doc_text(raw_text: str, fallback_title: str) -> tuple[str, dict[str, str]]:
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
    }
    return full_text, normalized_fm


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync SourceMedium docs into Ragie")
    parser.add_argument("--partition", required=True, help="Ragie partition (e.g. shared_docs, tenant_acme)")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Sync mode (currently both modes use full diff-based reconciliation)",
    )
    parser.add_argument("--doc-ref", default="", help="Optional single docs ref to sync")
    parser.add_argument("--source", default="sourcemedium-docs", help="Managed metadata source marker")
    parser.add_argument("--repo-name", default="sourcemedium-docs", help="Repo name for metadata/external_id")
    parser.add_argument("--docs-base-url", default="https://docs.sourcemedium.com", help="Base URL for url_full metadata")
    parser.add_argument("--base-url", default="https://api.ragie.ai", help="Ragie API base URL")
    parser.add_argument("--commit-sha", default="", help="Commit SHA to stamp in metadata")
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
    if args.doc_ref:
        ref = args.doc_ref.lstrip("/")
        refs = [r for r in refs if r == ref]
        if not refs:
            raise SyncError(f"doc_ref '{args.doc_ref}' not found in docs.json navigation")

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

    stale_external_ids = sorted(set(remote_by_external.keys()) - set(local_by_external.keys()))
    stale_docs = [remote_by_external[eid] for eid in stale_external_ids]

    stale_no_external_docs: list[dict[str, Any]] = []
    skipped_no_external = 0
    for doc in remote_without_external:
        metadata = doc.get("metadata") or {}
        docs_ref = str(metadata.get("docs_ref") or "").strip()
        if docs_ref and docs_ref not in local_refs:
            stale_no_external_docs.append(doc)
        else:
            skipped_no_external += 1

    log(
        "[INFO] Plan: "
        f"create={len(create_docs)} "
        f"update_raw={len(update_raw_docs)} "
        f"patch_metadata={len(patch_metadata_docs)} "
        f"delete_stale={len(stale_docs)} "
        f"delete_duplicates={len(duplicate_docs)} "
        f"delete_stale_no_external={len(stale_no_external_docs)}"
    )
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as err:
        log(f"[ERROR] {err}")
        raise SystemExit(1)
