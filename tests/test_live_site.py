#!/usr/bin/env python3
"""
Post-deployment validation tests for SourceMedium documentation site.

This test suite validates that:
1. All navigation links in docs.json resolve to live pages
2. Internal links within pages work correctly
3. Key pages load with expected content
4. No 404s or server errors

Usage:
    # Run all tests
    pytest tests/test_live_site.py -v

    # By default, live tests are excluded (see tests/pytest.ini)
    # Run live tests explicitly:
    pytest tests/test_live_site.py -v -m live

    # Run specific test category
    pytest tests/test_live_site.py -v -k "navigation"

    # Run against staging (default is production)
    DOCS_BASE_URL=https://staging.docs.sourcemedium.com pytest tests/test_live_site.py -v

Requirements:
    pip install pytest requests
"""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
import requests

# Configuration
BASE_URL = os.environ.get("DOCS_BASE_URL", "https://docs.sourcemedium.com").rstrip("/")
TIMEOUT = float(os.environ.get("DOCS_TIMEOUT", "10"))
MAX_WORKERS = int(os.environ.get("DOCS_MAX_WORKERS", "8"))
FAIL_ON_REDIRECT_LOOPS = os.environ.get("DOCS_FAIL_ON_REDIRECT_LOOPS", "0") == "1"
VERIFY_GIT_SHA = os.environ.get("DOCS_VERIFY_GIT_SHA", "0") == "1"
REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "sourcemedium-docs-live-tests/1.0 (+https://docs.sourcemedium.com)",
        }
    )

    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    except Exception:
        # Keep a plain session if retry wiring isn't available.
        pass

    return session


def normalize_route(ref: str) -> str:
    """
    Normalize a docs route/path for consistent comparisons.

    - Ensure leading slash
    - Remove query + fragment
    - Remove trailing slash (except root)
    """
    clean = ref.strip()
    if not clean:
        return clean
    clean = clean.split("#", 1)[0].split("?", 1)[0]
    if not clean.startswith("/"):
        clean = "/" + clean
    if clean != "/":
        clean = clean.rstrip("/")
    return clean


def strip_fenced_code_blocks(content: str) -> str:
    # Remove triple-backtick fenced blocks to avoid false-positive links inside examples.
    return re.sub(r"```.*?```", "", content, flags=re.DOTALL)


def is_asset_path(path: str) -> bool:
    # Skip paths that point to static assets, not documentation pages.
    asset_prefixes = ("/images/", "/logo/", "/favicon.", "/snippets/")
    if path.startswith(asset_prefixes):
        return True
    # If it looks like a direct file link (has an extension), treat as asset.
    return bool(re.search(r"/[^/]+\.[a-zA-Z0-9]{2,5}$", path))


def extract_vercel_deployment_id(response: requests.Response) -> str | None:
    """
    Mintlify sites are typically hosted on Vercel and often expose a Vercel deployment
    identifier via response headers.

    We prefer the final response, but some deployments only include the header on
    a redirect response in the chain.
    """
    header_keys = ("x-served-version", "x-version")
    for key in header_keys:
        value = response.headers.get(key)
        if value:
            return value
    for prior in reversed(response.history or []):
        for key in header_keys:
            value = prior.headers.get(key)
            if value:
                return value
    return None


def get_local_git_sha() -> str | None:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return sha if sha else None
    except Exception:
        return None


def get_vercel_deployment_git_sha(deployment_id: str) -> str | None:
    """
    If a Vercel token is available, resolve the deployment ID -> git commit SHA.

    Requires `VERCEL_TOKEN` with access to the project owning the deployment.
    """
    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        return None
    url = f"https://api.vercel.com/v13/deployments/{deployment_id}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if not isinstance(data, dict):
        return None
    # Prefer explicit gitSource.sha when present.
    git_source = data.get("gitSource")
    if isinstance(git_source, dict):
        sha = git_source.get("sha")
        if isinstance(sha, str) and sha:
            return sha
    # Fallback: some responses include `meta` fields.
    meta = data.get("meta")
    if isinstance(meta, dict):
        for key in ("githubCommitSha", "gitSha", "commitSha"):
            sha = meta.get(key)
            if isinstance(sha, str) and sha:
                return sha
    return None


class TestDeploymentVersion:
    """Verify we are testing the expected deployed version."""

    @pytest.mark.live
    def test_deployment_id_is_available(self, http_session: requests.Session):
        resp = http_session.get(BASE_URL, timeout=TIMEOUT, allow_redirects=True)
        assert resp.status_code == 200, f"Base URL returned {resp.status_code}"

        deployment_id = extract_vercel_deployment_id(resp)
        assert deployment_id, "Could not find Vercel deployment id (x-served-version/x-version)"

        expected_deployment = os.environ.get("DOCS_EXPECTED_VERCEL_DEPLOYMENT_ID")
        if expected_deployment:
            assert (
                deployment_id == expected_deployment
            ), f"Expected deployment {expected_deployment}, got {deployment_id}"

        if VERIFY_GIT_SHA:
            local_sha = get_local_git_sha()
            assert local_sha, "Could not determine local git SHA for docs repo"
            vercel_sha = get_vercel_deployment_git_sha(deployment_id)
            if not vercel_sha:
                pytest.skip("VERCEL_TOKEN missing or deployment git SHA not available via Vercel API")
            assert (
                vercel_sha == local_sha
            ), f"Live site git SHA {vercel_sha} does not match local {local_sha}"


class TestSiteAvailability:
    """Basic site health checks."""

    @pytest.mark.live
    def test_homepage_loads(self, http_session: requests.Session):
        """Homepage should return 200 and contain expected content."""
        response = http_session.get(BASE_URL, timeout=TIMEOUT, allow_redirects=True)
        assert response.status_code == 200, f"Homepage returned {response.status_code}"
        assert re.search(r"Source\s*Medium", response.text, flags=re.IGNORECASE), (
            "Homepage missing SourceMedium branding"
        )

    @pytest.mark.live
    def test_robots_txt(self, http_session: requests.Session):
        """Robots.txt should be accessible."""
        response = http_session.get(f"{BASE_URL}/robots.txt", timeout=TIMEOUT, allow_redirects=True)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"


class TestNavigationLinks:
    """Validate all navigation links from docs.json resolve to live pages."""

    @staticmethod
    def extract_page_refs(obj: dict | list | str, refs: list | None = None) -> list[str]:
        """Recursively extract page references from docs.json structure."""
        if refs is None:
            refs = []

        if isinstance(obj, str):
            # Skip external URLs and anchors
            if not obj.startswith(("http://", "https://", "#")):
                refs.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                TestNavigationLinks.extract_page_refs(item, refs)
        elif isinstance(obj, dict):
            # Check for page references in navigation structure
            for key in ["pages", "tabs", "groups", "navigation"]:
                if key in obj:
                    TestNavigationLinks.extract_page_refs(obj[key], refs)
            # Also check 'href' in card-style references
            if "href" in obj and not obj["href"].startswith(("http://", "https://")):
                refs.append(obj["href"])

        return refs

    @pytest.fixture(scope="class")
    def docs_json(self) -> dict:
        """Load docs.json navigation config."""
        docs_json_path = REPO_ROOT / "docs.json"
        assert docs_json_path.exists(), f"docs.json not found at {docs_json_path}"
        with open(docs_json_path) as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def page_refs(self, docs_json: dict) -> list[str]:
        """Extract all page references from docs.json."""
        refs = self.extract_page_refs(docs_json)
        # Deduplicate while preserving order
        seen = set()
        unique_refs = []
        for ref in refs:
            norm = normalize_route(ref)
            if norm and norm not in seen:
                seen.add(norm)
                unique_refs.append(norm)
        return unique_refs

    def test_docs_json_valid(self, docs_json: dict):
        """docs.json should be valid and have expected structure."""
        assert "navigation" in docs_json or "tabs" in docs_json, "Missing navigation structure"

    def test_all_nav_pages_exist_locally(self, page_refs: list[str]):
        """All navigation refs should have corresponding .mdx files."""
        missing = []
        for ref in page_refs:
            clean_ref = ref.lstrip("/")
            mdx_path = REPO_ROOT / f"{clean_ref}.mdx"
            index_path = REPO_ROOT / clean_ref / "index.mdx"
            if not mdx_path.exists() and not index_path.exists():
                missing.append(ref)

        assert not missing, f"Missing .mdx files for nav refs: {missing[:10]}{'...' if len(missing) > 10 else ''}"

    @pytest.mark.live
    def test_nav_pages_load_on_site(self, http_session: requests.Session, page_refs: list[str]):
        """All navigation pages should load successfully on live site."""
        failed = []
        warnings = []

        def fetch(ref: str):
            url = urljoin(BASE_URL + "/", ref.lstrip("/"))
            try:
                response = http_session.get(url, timeout=TIMEOUT, allow_redirects=True)
                return ref, response.status_code, None
            except requests.TooManyRedirects:
                return ref, None, "redirect loop"
            except requests.RequestException as e:
                return ref, None, str(e)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch, ref) for ref in page_refs]
            for fut in as_completed(futures):
                ref, status_code, err = fut.result()
                if err == "redirect loop":
                    if FAIL_ON_REDIRECT_LOOPS:
                        failed.append((ref, "redirect loop"))
                    else:
                        warnings.append((ref, "redirect loop"))
                elif err is not None:
                    failed.append((ref, err))
                elif status_code != 200:
                    failed.append((ref, status_code))

        # Print warnings but don't fail on redirect loops (site-side issue)
        if warnings:
            warning_msg = "\n".join([f"  {ref}: {status}" for ref, status in warnings])
            print(f"\nWARNING: Site redirect issues (not doc issues):\n{warning_msg}")

        if failed:
            failure_msg = "\n".join([f"  {ref}: {status}" for ref, status in failed[:20]])
            pytest.fail(f"Navigation pages failed to load:\n{failure_msg}")


class TestInternalLinks:
    """Validate internal links within MDX files."""

    @staticmethod
    def extract_internal_links(mdx_content: str) -> list[str]:
        """Extract internal links from MDX content."""
        mdx_content = strip_fenced_code_blocks(mdx_content)
        links = []

        # Markdown links: [text](/path) or [text](path)
        md_links = re.findall(r'\[([^\]]*)\]\((/[^)#]+)', mdx_content)
        links.extend([link for _, link in md_links])

        # href attributes: href="/path" or href='/path'
        href_links = re.findall(r'href=["\'](/[^"\'#]+)', mdx_content)
        links.extend(href_links)

        # Filter out external links and anchors
        internal_links = []
        for link in links:
            link = normalize_route(link)
            if not link or link.startswith(("http://", "https://", "#")):
                continue
            if is_asset_path(link):
                continue
            internal_links.append(link)

        return list(set(internal_links))

    @pytest.fixture(scope="class")
    def redirect_sources(self) -> set[str]:
        """Load redirect source paths from docs.json."""
        docs_json_path = REPO_ROOT / "docs.json"
        if not docs_json_path.exists():
            return set()
        with open(docs_json_path) as f:
            data = json.load(f)
        redirects = data.get("redirects", [])
        return {r.get("source", "").rstrip("/") for r in redirects}

    @pytest.fixture(scope="class")
    def all_mdx_files(self) -> list[Path]:
        """Get all MDX files in the repo."""
        return list(REPO_ROOT.glob("**/*.mdx"))

    def test_internal_links_have_targets(self, all_mdx_files: list[Path], redirect_sources: set[str]):
        """All internal links should point to existing files or valid redirects."""
        broken_links = []

        for mdx_file in all_mdx_files:
            content = mdx_file.read_text(encoding="utf-8", errors="ignore")
            links = self.extract_internal_links(content)

            for link in links:
                # Normalize link for comparison
                normalized_link = normalize_route(link)

                # Skip if this link has a redirect configured
                if normalized_link in redirect_sources:
                    continue

                # Remove leading slash and add .mdx extension
                clean_link = normalized_link.lstrip("/")
                target_path = REPO_ROOT / f"{clean_link}.mdx"

                # Also check without .mdx for index files
                target_index = REPO_ROOT / clean_link / "index.mdx"

                if not target_path.exists() and not target_index.exists():
                    # Check if it's a directory with content
                    target_dir = REPO_ROOT / clean_link
                    if not target_dir.is_dir():
                        rel_file = mdx_file.relative_to(REPO_ROOT)
                        broken_links.append(f"{rel_file}: {normalized_link}")

        if broken_links:
            msg = "\n".join(broken_links[:20])
            pytest.fail(f"Broken internal links found:\n{msg}")


class TestTableDocumentation:
    """Validate sm_transformed_v2 table documentation."""

    TABLE_DOCS_PATH = REPO_ROOT / "data-activation" / "data-tables" / "sm_transformed_v2"

    @pytest.fixture(scope="class")
    def table_doc_files(self) -> list[Path]:
        """Get all table documentation files."""
        if not self.TABLE_DOCS_PATH.exists():
            pytest.skip("Table docs directory not found")
        return list(self.TABLE_DOCS_PATH.glob("*.mdx"))

    def test_table_docs_have_required_frontmatter(self, table_doc_files: list[Path]):
        """All table docs should have title and description."""
        missing_frontmatter = []

        for doc_file in table_doc_files:
            content = doc_file.read_text()

            # Check for frontmatter
            if not content.startswith("---"):
                missing_frontmatter.append(f"{doc_file.name}: No frontmatter")
                continue

            # Extract frontmatter
            parts = content.split("---", 2)
            if len(parts) < 3:
                missing_frontmatter.append(f"{doc_file.name}: Invalid frontmatter")
                continue

            frontmatter = parts[1]
            if "title:" not in frontmatter:
                missing_frontmatter.append(f"{doc_file.name}: Missing title")
            if "description:" not in frontmatter:
                missing_frontmatter.append(f"{doc_file.name}: Missing description")

        assert not missing_frontmatter, f"Frontmatter issues:\n" + "\n".join(missing_frontmatter)

    def test_no_excluded_columns_documented(self, table_doc_files: list[Path]):
        """Table docs should not document MDW-excluded columns."""
        # Columns that should never appear in docs
        excluded_patterns = [
            r"name:\s*\w+_array\b",  # _array suffix columns
            r"name:\s*_synced_at\b",  # _synced_at columns
            r"name:\s*sm_order_referrer_source\b",  # explicitly excluded
        ]

        violations = []

        for doc_file in table_doc_files:
            content = doc_file.read_text(encoding="utf-8", errors="ignore")
            # Only scan YAML blocks to avoid matching prose/examples.
            yaml_blocks = re.findall(r"```yaml\\s*(.*?)\\s*```", content, flags=re.DOTALL)
            haystack = "\n".join(yaml_blocks) if yaml_blocks else content

            for pattern in excluded_patterns:
                matches = re.findall(pattern, haystack)
                if matches:
                    violations.append(f"{doc_file.name}: Found excluded column(s): {matches}")

        assert not violations, f"Excluded columns found in docs:\n" + "\n".join(violations)

    def test_no_masterset_references(self, table_doc_files: list[Path]):
        """Table docs should use sm_transformed_v2, not masterset."""
        violations = []

        for doc_file in table_doc_files:
            content = doc_file.read_text(encoding="utf-8", errors="ignore")

            if "masterset" in content.lower():
                violations.append(doc_file.name)

        assert not violations, f"Files referencing 'masterset' (should be sm_transformed_v2): {violations}"

    @pytest.mark.live
    def test_table_doc_pages_load(self, http_session: requests.Session, table_doc_files: list[Path]):
        """All table doc pages should load on live site."""
        failed = []

        def fetch(doc_file: Path):
            rel_path = doc_file.relative_to(REPO_ROOT).with_suffix("")
            url = urljoin(BASE_URL + "/", str(rel_path))
            try:
                response = http_session.get(url, timeout=TIMEOUT, allow_redirects=True)
                return doc_file.name, response.status_code, None
            except requests.TooManyRedirects:
                return doc_file.name, None, "redirect loop"
            except requests.RequestException as e:
                return doc_file.name, None, str(e)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch, doc_file) for doc_file in table_doc_files]
            for fut in as_completed(futures):
                name, status_code, err = fut.result()
                if err == "redirect loop":
                    if FAIL_ON_REDIRECT_LOOPS:
                        failed.append((name, "redirect loop"))
                elif err is not None:
                    failed.append((name, err))
                elif status_code != 200:
                    failed.append((name, status_code))

        if failed:
            msg = "\n".join([f"  {name}: {status}" for name, status in failed])
            pytest.fail(f"Table doc pages failed to load:\n{msg}")


class TestKeyPages:
    """Validate critical pages load with expected content."""

    KEY_PAGES = [
        ("/data-activation/data-tables/sm_transformed_v2", "sm_transformed_v2"),
        ("/data-activation/managed-data-warehouse/modeling", "SQL"),
        ("/onboarding/data-docs/dimensions", "dimension"),
        ("/help-center/common-analyses/roas", "ROAS"),
    ]

    @pytest.mark.live
    @pytest.mark.parametrize("path,expected_content", KEY_PAGES)
    def test_key_page_loads_with_content(self, http_session: requests.Session, path: str, expected_content: str):
        """Key pages should load and contain expected content."""
        url = urljoin(BASE_URL, path)
        response = http_session.get(url, timeout=TIMEOUT, allow_redirects=True)

        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert expected_content.lower() in response.text.lower(), (
            f"{path} missing expected content: '{expected_content}'"
        )


class TestSQLExamples:
    """Validate SQL examples use correct dataset naming."""

    @pytest.fixture(scope="class")
    def modeling_doc(self) -> str:
        """Load modeling.mdx content."""
        modeling_path = REPO_ROOT / "data-activation" / "managed-data-warehouse" / "modeling.mdx"
        if not modeling_path.exists():
            pytest.skip("modeling.mdx not found")
        return modeling_path.read_text()

    def test_sql_uses_sm_transformed_v2(self, modeling_doc: str):
        """SQL examples should reference sm_transformed_v2, not masterset."""
        # Check for masterset in SQL blocks
        sql_blocks = re.findall(r"```sql\n(.*?)```", modeling_doc, re.DOTALL)

        for i, sql in enumerate(sql_blocks):
            assert "masterset" not in sql.lower(), (
                f"SQL block {i+1} references 'masterset' instead of 'sm_transformed_v2'"
            )

    def test_sql_has_correct_dataset_pattern(self, modeling_doc: str):
        """SQL examples should use your_project.sm_transformed_v2.table pattern."""
        sql_blocks = re.findall(r"```sql\\s*(.*?)\\s*```", modeling_doc, re.DOTALL)
        haystack = "\n".join(sql_blocks)
        table_refs = re.findall(r'(?:from|join)\\s+`?([^\\s`]+)`?', haystack, re.IGNORECASE)

        for ref in table_refs:
            if "your_project" in ref.lower():
                assert "sm_transformed_v2" in ref, (
                    f"Table reference '{ref}' should use sm_transformed_v2 dataset"
                )


# Pytest configuration
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: marks tests that hit the live site (may be slow)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
