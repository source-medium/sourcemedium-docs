# Custom Objects Update Skill - Implementation Plan

## Overview

This skill (`/custom-objects-update`) fetches the latest custom object data from each active MDW tenant and updates the tenant documentation pages in `mintlify/tenants/`.

## Design Decisions (Finalized)

### 1. Tenant Discovery: Auto-scaffold missing tenants ✅

**Approach:** Hybrid discovery with auto-scaffolding
- **Primary:** Check known MDW tenant IDs from `dbt_project.yml` config
- **Secondary:** Scan existing `mintlify/tenants/*.mdx` files
- **Action:** For any tenant with BQ data but no docs → **auto-create both pages**

This ensures new tenants are automatically documented without manual intervention.

### 2. Object Descriptions: LLM-powered ✅

**Approach:** Generate intelligent descriptions using:
- Object name pattern analysis (`*_summary`, `obt_*`, `rpt_*`, etc.)
- Dataset context (`customized_views`, `klaviyo`, `northbeam_data`)
- DDL analysis when available (column names, aggregation patterns)

Example outputs:
- `orders_and_ads_summary` → "Aggregated daily summary joining order metrics with advertising spend data."
- `dsp_native` → "Raw Amazon DSP advertising data containing campaign-level spend and performance metrics."

### 3. Execution: Parallel with throttling ✅

**Approach:** Run up to 5 concurrent BQ queries using `xargs -P 5`
- Reduces total runtime from ~60s to ~15s for 20 tenants
- Avoids BQ rate limiting with conservative concurrency
- Graceful error handling for failed queries

### 4. Git Integration: Report and wait ✅

**Approach:** No automatic commits
- Write all files
- Display comprehensive summary with changes
- Wait for user to review
- User explicitly requests commit when ready

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     /custom-objects-update                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. DISCOVER TENANTS                                            │
│     ├── Known MDW tenant IDs (from config)                      │
│     ├── Existing docs (scan tenants/*.mdx)                      │
│     └── Compare → identify NEW tenants to scaffold              │
│                                                                  │
│  2. AUTO-SCAFFOLD NEW TENANTS                                   │
│     ├── Create {tenant_id}.mdx (overview page)                  │
│     └── Create {tenant_id}/custom-objects.mdx (placeholder)     │
│                                                                  │
│  3. FETCH DATA (PARALLEL, 5 concurrent)                         │
│     └── For each tenant:                                        │
│         Query: sm-{tenant}.sm_metadata.dim_tenant_custom_objects│
│         - Filter: latest snapshot_at                            │
│         - Filter: classification IN (tenant_dataset_custom,     │
│                   tenant_or_legacy_in_standard_dataset)         │
│                                                                  │
│  4. TRANSFORM & GENERATE DESCRIPTIONS                           │
│     ├── Group by dataset_id, aggregate stats                    │
│     └── LLM-generate descriptions from name/DDL/context         │
│                                                                  │
│  5. WRITE FILES                                                 │
│     ├── tenants/{tenant_id}/custom-objects.mdx                  │
│     ├── tenants/{tenant_id}.mdx (if new)                        │
│     └── tenants/README.md (update counts)                       │
│                                                                  │
│  6. REPORT & WAIT                                               │
│     ├── Summary table: tenant, objects, status, changes         │
│     ├── List of files modified                                  │
│     └── Wait for user confirmation before any git ops           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
mintlify/.claude/skills/custom-objects-update/
├── SKILL.md              # Main skill instructions (429 lines)
└── PLAN.md               # This design document
```

## Usage Examples

```bash
# Update all tenants
/custom-objects-update

# Update single tenant
/custom-objects-update neurogum

# Preview changes without writing
/custom-objects-update --dry-run

# List discovered tenants
/custom-objects-update --list

# Check for new tenants not yet documented
/custom-objects-update --discover
```

## BigQuery Query

```sql
WITH latest_snapshot AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY dataset_id, object_name
      ORDER BY snapshot_at DESC
    ) as rn
  FROM `sm-{tenant}.sm_metadata.dim_tenant_custom_objects`
  WHERE classification IN (
    'tenant_dataset_custom',
    'tenant_or_legacy_in_standard_dataset'
  )
)
SELECT
  dataset_id,
  object_name,
  object_type,
  CAST(job_count_180d AS INT64) as job_count_180d,
  FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', snapshot_at, 'America/New_York') as snapshot_at_est,
  ddl
FROM latest_snapshot
WHERE rn = 1
ORDER BY CAST(job_count_180d AS INT64) DESC
```

## Error Handling

| Scenario | Action |
|----------|--------|
| BQ auth failure | Stop immediately, show auth instructions |
| Table doesn't exist | Skip tenant, include in "Failed" report |
| Empty results (0 objects) | Generate page with notice |
| Network timeout | Retry once, then skip and report |
| Invalid MDX characters | Escape for compatibility |
| Parallel job fails | Collect error, continue with others |

## Dependencies

- `bq` CLI (BigQuery command-line tool)
- `gcloud` CLI for authentication
- Active GCP credentials with access to tenant projects
- Write access to mintlify/tenants/ directory

## Estimated Runtime

- ~2-3 seconds per tenant query
- ~15-20 seconds total with parallel execution (20 tenants)
- Description generation adds ~1-2 seconds per tenant

## Maintenance Notes

- **New tenants:** Automatically discovered and scaffolded
- **Churned tenants:** Manual cleanup needed (docs remain but data stops updating)
- **Refresh frequency:** Run weekly or after major tenant onboarding
