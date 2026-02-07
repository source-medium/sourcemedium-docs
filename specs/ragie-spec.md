# Ragie Docs Indexing + Tenant Partition Retrieval Spec

Status: Proposed
Owner: Docs + AI Analyst
Last updated: 2026-02-06

## 1) Goal

Create a production-ready Ragie indexing and retrieval pipeline for SourceMedium docs that:

1. Auto-indexes docs from this repo on push.
2. Supports idempotent upsert and stale-doc deletion.
3. Enforces strict tenant isolation with Ragie partitions.
4. Exposes retrieval primitives we can use to "RAG out" answers safely.

## 2) Scope

### In scope

- Index published docs from this repo into Ragie.
- Use Ragie REST API directly (no CLI dependency in v1).
- Add tenant-partition retrieval contract (`partition = tenant_id mapping`).
- Enable partition context-aware retrieval metadata (`description`, `context_aware`, `metadata_schema`).
- Enable partition-scoped entity extraction instructions for docs.
- Define automation workflow and acceptance tests.

### Out of scope (v1)

- UI work in docs dashboard.
- Migrating historical non-doc knowledge sources.
- Building full answer orchestration in this repo (we define API contract only).

## 3) Verified Ragie API Contract (Source of Truth)

Base URL: `https://api.ragie.ai`
Auth: `Authorization: Bearer <RAGIE_API_KEY>`

OpenAPI confirms:

- `POST /documents` (multipart file upload)
- `POST /documents/raw` (ingest raw text/JSON)
- `POST /documents/url`
- `GET /documents` (paginated list)
- `GET /documents/{document_id}` (status/details)
- `PUT /documents/{document_id}/raw`
- `PUT /documents/{document_id}/file`
- `PATCH /documents/{document_id}/metadata`
- `DELETE /documents/{document_id}`
- `POST /retrievals`
- `GET/POST /partitions`, `GET/PATCH/DELETE /partitions/{partition_id}`
- `GET/POST /instructions`, `PUT/DELETE /instructions/{instruction_id}`
- `GET /documents/{document_id}/entities`
- `GET /instructions/{instruction_id}/entities`

Document lifecycle states (from endpoint docs):

- `pending`
- `partitioning`
- `partitioned`
- `refined`
- `chunked`
- `indexed`
- `summary_indexed`
- `keyword_indexed`
- `ready`
- `failed`

## 4) Constraints From This Repo

- This repo is mostly `.mdx` pages (`316` files), with very few `.md` files.
- Ragie file upload supports `.md` but does not list `.mdx` as a supported file extension.

Decision:

- Use `POST /documents/raw` and `PUT /documents/{id}/raw` for v1 indexing.
- Convert MDX source into clean text before upload.

This avoids extension mismatch risk and gives deterministic content shaping.

## 5) Partition Strategy (Tenant Isolation)

### Hard requirements

- Every write MUST include `partition`.
- Every retrieval MUST include `partition`.
- The partition MUST be server-derived from authenticated tenant context.
- Never trust client-provided partition directly.
- Any docs under `/tenants/` MUST be hard partitioned:
  - `tenants/<slug>...` docs are only indexed into `tenant_<slug>`
  - shared/non-tenant partitions must never contain `/tenants/` docs

OpenAPI behavior note:

- If `partition` is omitted, account behavior differs by account age (accounts created after 2025-01-09 default-scope, older accounts may scope more broadly unless configured).
- Because of this ambiguity, our implementation treats missing partition as a hard error.

### Partition format

- Regex: `^[a-z0-9_-]+$` (matches Ragie rules)
- Canonical form: `tenant_<tenant_id_normalized>`

Examples:

- `tenant_acme`
- `tenant_12345`

### Shared docs behavior

Two supported modes:

1. Strict tenant-only mode (default for security-sensitive workflows):
   - Query only `tenant_<id>`.
   - Guarantees no cross-tenant retrieval.
2. Tenant + shared fallback mode (optional):
   - First query `tenant_<id>`.
   - If no useful chunks, query `shared_docs`.
   - Keep responses labeled by source partition.

If we need shared docs visible in strict mode, duplicate shared docs into each tenant partition during provisioning.

## 6) Document Identity + Metadata Contract

### Identity

- `external_id` is required in practice for idempotent sync.
- Use a stable, partition-safe value:
  - `external_id = "repo:sourcemedium-docs|partition:<partition>|ref:<docs_ref>"`

### Name

- Use stable path-like name, not title:
  - `name = <docs_ref>`

This avoids rename churn when titles change.

### Metadata keys (custom)

- `source`: `sourcemedium-docs`
- `repo`: `sourcemedium-docs`
- `docs_ref`: `data-activation/template-resources/sql-query-library`
- `url_path`: `/data-activation/template-resources/sql-query-library`
- `url_full`: `https://docs.sourcemedium.com/data-activation/template-resources/sql-query-library`
- `title`: frontmatter title
- `description`: frontmatter description
- `content_hash`: sha256 of normalized text
- `commit_sha`: git SHA used for sync
- `visibility`: `tenant` or `shared`
- `tenant_id`: normalized tenant id (for tenant partitions)

Do not use Ragie reserved keys:

- `document_id`
- `document_type`
- `document_source`
- `document_name`
- `document_uploaded_at`
- `start_time`
- `end_time`
- `chunk_content_type`

## 7) Ingestion Input Selection

### Source of truth for pages

Use `docs.json` navigation references, not a blind filesystem glob.

Reason:

- Only published pages should be indexed.
- Prevent indexing orphan/internal files unintentionally.

### Inclusion

- Paths referenced by `docs.json` that resolve to `<ref>.mdx` or `<ref>.md`.

### Exclusion

- `snippets/`
- `specs/`
- hidden/internal operational files

## 8) MDX Normalization Rules (for `/documents/raw`)

Input: raw `.mdx` file
Output: deterministic plain text optimized for retrieval

Normalization pipeline:

1. Parse frontmatter.
2. Build preamble:
   - `# <title>`
   - `<description>`
3. Remove frontmatter block from body.
4. Remove `import` / `export` lines.
5. Convert known Mintlify callouts:
   - `<Info>...</Info>` -> `Info: ...`
   - `<Tip>...</Tip>` -> `Tip: ...`
   - `<Note>...</Note>` -> `Note: ...`
   - `<Warning>...</Warning>` -> `Warning: ...`
6. Strip remaining JSX tags while keeping textual children.
7. Preserve headings, lists, code fences, and links.
8. Normalize whitespace and line endings.

Store `content_hash` of final normalized text in metadata.

## 9) Sync Algorithm (Idempotent)

Per partition sync run:

1. Optionally ensure partition config with `PATCH /partitions/{partition_id}`:
   - `context_aware = true`
   - `description` (partition summary)
   - `metadata_schema` (filter-friendly schema for our metadata keys)
2. Optionally ensure entity instruction exists (`POST /instructions`) scoped to partition.
3. Load local docs set from `docs.json`.
4. Normalize each local doc to text.
5. Build local map by `external_id`.
6. Fetch all remote docs in partition via `GET /documents` pagination.
7. Build remote map by `external_id` (client-side filter `metadata.source == sourcemedium-docs`).
8. For each local doc:
   - Not in remote -> `POST /documents/raw`.
   - In remote and hash changed -> `PUT /documents/{id}/raw`.
   - In remote and metadata changed -> `PATCH /documents/{id}/metadata`.
9. For each remote doc absent locally -> `DELETE /documents/{id}?async=true`.
10. Poll changed docs (`GET /documents/{id}`) until terminal:
   - success: `ready` (or optionally `indexed` for faster CI)
   - failure: `failed` -> fail job with doc id + errors.

## 10) GitHub Actions Design

Workflow file: `.github/workflows/ragie-index.yml`

Triggers:

- `push` to `main`/`master` when docs files or `docs.json` change.
- `workflow_dispatch` with inputs:
  - `partition` (default `shared_docs`)
  - `mode` (`incremental`/`full`)
  - `doc_ref` (optional single page)
  - `ensure_partition_context_aware` (`true/false`)
  - `ensure_entity_instruction` (`true/false`)

Secrets and vars:

- Secret: `RAGIE_API_KEY`
- Variable (or workflow input): `RAGIE_PARTITION`
- Optional vars: `RAGIE_ENSURE_PARTITION_CONTEXT_AWARE`, `RAGIE_ENSURE_ENTITY_INSTRUCTION`

Execution steps:

1. Checkout repo.
2. Set up Python runtime.
3. Install script deps (minimal stdlib + `requests` + frontmatter parser).
4. Run shared (or input-selected) partition sync:
   - `python scripts/ragie_sync.py --partition "$RAGIE_PARTITION" --mode incremental --ensure-partition-context-aware --ensure-entity-instruction`
5. On push, detect changed tenant slugs from `tenants/**` paths and run:
   - `python scripts/ragie_sync.py --partition "tenant_<slug>" --mode incremental --ensure-partition-context-aware --ensure-entity-instruction`

For tenant-specific sync jobs (if we run them in CI):

- one run per tenant partition, or
- one orchestrator job that iterates tenant list from secure source.

## 11) Retrieval Contract (App Side)

### API request to Ragie

`POST /retrievals`

Body (minimum):

- `query` (required)
- `partition` (required by our policy)

Recommended defaults:

- `top_k = 8`
- `rerank = true`
- `max_chunks_per_document = 2`
- `recency_bias = false`

Optional `filter` supports metadata operators:

- `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`

### Retrieval wrapper requirements

Our server wrapper MUST:

1. Derive `partition` from authenticated tenant context.
2. Reject requests with missing tenant context.
3. Never allow arbitrary partition override from client payload.
4. Log request id, tenant id, partition, top_k, latency, chunk count.

### Context-aware partition requirements

For each active partition, keep these fields set:

- `context_aware = true`
- `description` with concise scope summary
- `metadata_schema` describing filterable metadata keys (`content_type`, `primary_surface`, `surfaces`, `topic_tags`, etc.)

This improves Ragie’s dynamic filter-generation quality when using metadata-driven retrieval.

### Entity extraction requirements

- Create one partition-scoped instruction:
  - `name`: deterministic (`sourcemedium-doc-entities-v1-<partition>`)
  - `scope`: `document`
  - `partition`: target partition
  - `filter`: `{source == sourcemedium-docs, repo == sourcemedium-docs}`
  - `entity_schema`: arrays for `surfaces`, `keywords`, `table_names`, `column_names`, `dashboard_modules`, `integration_platforms`
- Read extracted entities via:
  - `GET /documents/{document_id}/entities`
  - `GET /instructions/{instruction_id}/entities`

### Expected response fields from Ragie

`scored_chunks[]` includes:

- `text`
- `score`
- `id`
- `index`
- `document_id`
- `document_name`
- `document_metadata`
- `links`

## 12) Answer Generation Strategy

### Preferred (v1)

- Use Ragie retrieval + our LLM completion layer.
- Pass top chunks with citations (`document_name`, `url_full` metadata).

### Optional (v2)

- Evaluate Ragie `POST /responses` for native generated answers.
- Constraint: current model support in docs is `deep-search`.

## 13) Security Requirements

1. `RAGIE_API_KEY` only in secrets manager / CI secret.
2. Never expose API key in client-side code.
3. Partition is mandatory on write/read.
4. Enforce tenant->partition mapping server-side.
5. Add alerting on retrievals missing partition (should be zero).

## 14) Observability + Ops

Track metrics:

- docs indexed created/updated/deleted per run
- indexing latency to `ready`
- failed document count + ids
- retrieval latency p50/p95
- empty retrieval rate by tenant
- cross-partition leakage test pass rate

Operational playbooks:

- Backfill: run `workflow_dispatch` with `mode=full`.
- Reindex single doc: script flag `--doc-ref <ref>`.
- Partition cleanup: `DELETE /partitions/{partition_id}` only by admin workflow.

## 15) Acceptance Criteria

### Indexing

1. Push changing one doc updates exactly one Ragie document in target partition.
2. Deleting a doc removes the corresponding Ragie document.
3. No duplicate active documents for same `external_id` + partition.
4. Failed indexing returns non-zero CI exit.

### Multi-tenancy

1. Doc ingested into `tenant_a` is not retrievable from `tenant_b`.
2. Retrieval requests without partition are rejected by our wrapper.
3. Tenant partition names always satisfy `^[a-z0-9_-]+$`.
4. Docs under `/tenants/<slug>` never appear in `shared_docs`.

### Partition intelligence

1. Partition has `context_aware=true` after sync bootstrap.
2. Partition description and metadata schema match expected template.
3. Partition-scoped instruction exists and is active.

### Entity extraction

1. New/updated docs in partition produce entities for the configured instruction.
2. Entity payload validates against configured `entity_schema`.

### Retrieval quality

1. Top chunks include correct `url_full` citation metadata.
2. Known test queries return at least one relevant chunk.

## 16) Implementation Plan

### Phase 1: Core sync script

- Add `scripts/ragie_sync.py` with:
  - docs.json page discovery
  - MDX normalization
  - create/update/delete sync
  - polling + failure reporting

### Phase 2: CI automation

- Add `.github/workflows/ragie-index.yml`.
- Add secret wiring docs in README/ops notes.

### Phase 3: Retrieval wrapper integration

- Add server-side retrieval client in app repo.
- Enforce tenant->partition mapping middleware.

### Phase 4: Validation + canary

- Run shared partition backfill.
- Run tenant canary partitions.
- Validate isolation test suite before production enablement.

## 17) cURL Reference Examples

### Create raw document in tenant partition

```bash
curl --request POST \
  --url https://api.ragie.ai/documents/raw \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header 'Content-Type: application/json' \
  --data @- <<'JSON'
{
  "name": "onboarding/getting-started/intro-to-sm",
  "external_id": "repo:sourcemedium-docs|partition:tenant_acme|ref:onboarding/getting-started/intro-to-sm",
  "partition": "tenant_acme",
  "metadata": {
    "source": "sourcemedium-docs",
    "repo": "sourcemedium-docs",
    "docs_ref": "onboarding/getting-started/intro-to-sm",
    "url_full": "https://docs.sourcemedium.com/onboarding/getting-started/intro-to-sm",
    "content_hash": "<sha256>"
  },
  "data": "# Intro to SourceMedium\\n...normalized content..."
}
JSON
```

### Retrieve with strict tenant partition

```bash
curl --request POST \
  --url https://api.ragie.ai/retrievals \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header 'Content-Type: application/json' \
  --data @- <<'JSON'
{
  "query": "How do I install the SDK?",
  "partition": "tenant_acme",
  "top_k": 8,
  "rerank": true,
  "max_chunks_per_document": 2
}
JSON
```

### Poll status for a changed document

```bash
curl --request GET \
  --url "https://api.ragie.ai/documents/<document_id>" \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header "partition: tenant_acme"
```

### Delete stale document

```bash
curl --request DELETE \
  --url "https://api.ragie.ai/documents/<document_id>?async=true" \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header "partition: tenant_acme"
```

### Enable context-aware partition settings

```bash
curl --request PATCH \
  --url "https://api.ragie.ai/partitions/tenant_acme" \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header 'Content-Type: application/json' \
  --data @- <<'JSON'
{
  "context_aware": true,
  "description": "SourceMedium tenant documentation partition for acme.",
  "metadata_schema": {
    "type": "object",
    "properties": {
      "content_type": {"type": "string"},
      "primary_surface": {"type": "string"},
      "surfaces": {"type": "array", "items": {"type": "string"}},
      "topic_tags": {"type": "array", "items": {"type": "string"}}
    }
  }
}
JSON
```

### Create partition-scoped entity extraction instruction

```bash
curl --request POST \
  --url https://api.ragie.ai/instructions \
  --header "Authorization: Bearer $RAGIE_API_KEY" \
  --header 'Content-Type: application/json' \
  --data @- <<'JSON'
{
  "name": "sourcemedium-doc-entities-v1-tenant_acme",
  "active": true,
  "scope": "document",
  "partition": "tenant_acme",
  "filter": {
    "source": {"$eq": "sourcemedium-docs"},
    "repo": {"$eq": "sourcemedium-docs"}
  },
  "prompt": "Extract analytics support entities...",
  "entity_schema": {
    "type": "object",
    "properties": {
      "surfaces": {"type": "array", "items": {"type": "string"}},
      "keywords": {"type": "array", "items": {"type": "string"}}
    }
  }
}
JSON
```

## 18) Risks and Mitigations

1. MDX component noise hurts retrieval quality.
   - Mitigation: normalization pipeline before `/documents/raw`.
2. Missing partition leads to accidental broad reads on older Ragie accounts.
   - Mitigation: hard fail when partition missing in our wrapper and sync scripts.
3. Duplicate docs from historical runs.
   - Mitigation: stable `external_id` + dedupe step in sync.
4. Long indexing tails for large updates.
   - Mitigation: async delete + bounded polling + retry/backoff.

## 19) Final Decision Log

1. Use Ragie REST API directly for v1 (`/documents/raw`, `/retrievals`) instead of CLI.
2. Use partition as mandatory tenant boundary.
3. Use docs.json-driven page discovery.
4. Use idempotent upsert + stale-delete sync model.
5. Keep answer generation outside this repo for v1 (retrieval contract first).

## 20) References

- Ragie Getting Started: `https://docs.ragie.ai/docs/getting-started`
- Ragie Create Document reference: `https://docs.ragie.ai/reference/createdocument`
- Ragie Retrieve reference: `https://docs.ragie.ai/reference/retrieve`
- Ragie Partitions guide: `https://docs.ragie.ai/docs/partitions`
- Ragie Context-Aware Descriptions: `https://docs.ragie.ai/docs/context-aware-descriptions`
- Ragie Entity Extraction guide: `https://docs.ragie.ai/docs/entity-extraction`
- Ragie OpenAPI schema used for endpoint/field validation: `https://api.ragie.ai/openapi.json`
