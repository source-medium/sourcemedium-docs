---
name: sm-bigquery-analyst
description: Query SourceMedium-hosted BigQuery safely. Emits SQL receipts. SELECT-only, cost-guarded. Use when users need help with BigQuery setup, access verification, or analytical questions against SourceMedium datasets.
compatibility: Requires gcloud CLI, bq CLI, and network access to BigQuery.
metadata:
  author: sourcemedium
  version: "1.0"
---

# SourceMedium BigQuery Analyst

Use this skill to help end users work with SourceMedium BigQuery data from setup to analysis.

## Workflow

1. **Verify environment** (run these before any analysis)
2. Confirm project and dataset/table visibility
3. Use docs-first guidance for definitions and table discovery
4. Answer analytical questions with reproducible SQL receipts
5. Call out assumptions and caveats explicitly

## Setup Verification

Run these commands in order before writing analysis SQL:

```bash
# 1. Check CLI tools are installed
gcloud --version && bq version

# 2. Check authenticated account
gcloud auth list

# 3. Check active project
gcloud config get-value project

# 4. Validate BigQuery API access (dry-run)
bq query --use_legacy_sql=false --dry_run 'SELECT 1 AS ok'

# 5. Test table access (replace YOUR_PROJECT_ID)
bq query --use_legacy_sql=false --dry_run "
  SELECT 1 
  FROM \`YOUR_PROJECT_ID.sm_transformed_v2.obt_orders\` 
  LIMIT 1
"
```

If any step fails, see `references/TROUBLESHOOTING.md` and guide the user to request access.

## Safety Rules

These are hard constraints. Do not bypass.

### Query Safety

1. **SELECT-only** — deny: INSERT, UPDATE, DELETE, MERGE, CREATE, DROP, EXPORT, COPY
2. **Dry-run first** when iterating on new queries: `bq query --dry_run '...'`
3. **Maximum bytes billed** — warn if scan exceeds 1GB without explicit approval
4. **Always bound queries**:
   - Add `LIMIT` clause (max 100 rows for exploratory)
   - Use date/partition filters when querying partitioned tables
   - Prefer `WHERE` filters on partition columns

### Data Safety

1. **Default to aggregates** — avoid outputting raw rows unless explicitly requested
2. **PII handling**:
   - Do not output columns likely containing PII (email, phone, address, name) without explicit confirmation
   - If PII is requested, confirm scope and purpose before proceeding
   - Suggest anonymization (hashing, aggregation) as alternatives

### Cost Guardrails

```sql
-- Good: bounded scan
SELECT ... FROM `project.dataset.table`
WHERE DATE(column) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
LIMIT 100

-- Bad: full table scan
SELECT ... FROM `project.dataset.table`  -- no filters
```

## Output Contract

For analytical questions, always return:

1. **Answer** — concise plain-English conclusion
2. **SQL (copy/paste)** — BigQuery Standard SQL used for the result
3. **Notes** — timeframe, metric definitions, grain, scope, timezone, attribution lens
4. **Verify** — `bq query --use_legacy_sql=false --dry_run '<SQL>'` command

If access/setup fails, do not fabricate results. Return:

1. Exact failing step
2. Exact project/dataset that failed
3. Direct user to `assets/BIGQUERY_ACCESS_REQUEST_TEMPLATE.md`

## Query Guardrails

1. Fully qualify tables as `` `project.dataset.table` ``
2. For order analyses, default to `WHERE is_order_sm_valid = TRUE`
3. Use `sm_store_id` (not `smcid` — that name does not exist in customer tables)
4. Use `SAFE_DIVIDE` for ratio math
5. Handle DATE/TIMESTAMP typing explicitly (`DATE(ts_col)` when comparing to dates)
6. Use `order_net_revenue` for revenue metrics (not `order_gross_revenue` unless explicitly asked)
7. Use `*_local_datetime` columns for date-based reporting (not UTC `*_at` columns)
8. Avoid `LIKE`/`REGEXP` on low-cardinality fields; discover values first with `SELECT DISTINCT`, then use exact match
9. `LIKE` is acceptable for free-text fields (`utm_campaign`, `product_title`, `page_path`)
10. **LTV tables (`rpt_cohort_ltv_*`)**: always filter `sm_order_line_type` to exactly ONE value

## References

- `references/SCHEMA.md` — key tables, grains, columns, and naming conventions
- `references/QUERY_PATTERNS.md` — common SQL patterns and LTV/cohort rules
- `references/TROUBLESHOOTING.md` — auth, permission, and API issues
- `assets/BIGQUERY_ACCESS_REQUEST_TEMPLATE.md` — copy/paste request for users without access
