# Review Guide: Tenant-Specific Documentation

## Overview

This PR adds hidden tenant-specific documentation pages to the Mintlify docs site. Each tenant gets an inventory of their custom BigQuery objects (tables/views) with usage statistics.

## What Changed

1. **New macro**: `generate_dim_tenant_custom_objects` - Inventories active custom objects in a tenant's BigQuery project (queried at least once in the past 180 days)
2. **New docs**: `mintlify/tenants/{tenant_id}/` - Hidden documentation pages for 16 tenants

## How to Review

### 1. Verify Data Accuracy

Pick 2-3 tenants and spot-check the documentation against actual BigQuery data.

**Important:** The table is partitioned by `snapshot_at` and may have multiple snapshots. Always filter to the latest snapshot to avoid double-counting:

```sql
-- Check custom objects for a tenant (latest snapshot only)
WITH latest AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY dataset_id, object_name ORDER BY snapshot_at DESC) as rn
  FROM `sm-{tenant}.sm_metadata.dim_tenant_custom_objects`
  WHERE classification IN ('tenant_dataset_custom', 'tenant_or_legacy_in_standard_dataset')
)
SELECT
  dataset_id,
  object_name,
  object_type,
  job_count_180d,
  last_used_at
FROM latest
WHERE rn = 1
ORDER BY CAST(job_count_180d AS INT64) DESC
LIMIT 20;
```

Compare the output with the corresponding `custom-objects.mdx` file.

### 2. Verify MDX Syntax

Run Mintlify validation locally:

```bash
cd mintlify
mintlify dev  # Start local server, check for errors
```

**Note:** `mintlify dev` requires Node.js LTS (18 or 20). It may crash on Node 25+.

Or just validate JSON:
```bash
python3 -m json.tool mintlify/docs.json
```

### 3. Check Hidden Page Behavior

After deploying to a staging environment:
1. Confirm pages are NOT visible in navigation
2. Confirm pages ARE accessible via direct URL
3. Check responsive layout on mobile

### 4. Spot-Check Content Quality

Review these files for formatting and content:

**High-usage tenant (complex):**
- `mintlify/tenants/zbiotics/custom-objects.mdx` - Has 100+ objects across many datasets

**Medium-usage tenant:**
- `mintlify/tenants/neurogum/custom-objects.mdx` - Has ~46 objects, manually enhanced

**Low-usage tenant:**
- `mintlify/tenants/catalinacrunch/custom-objects.mdx` - Has only 7 objects

### 5. Verify Classification Logic

The macro classifies objects into categories. Verify these make sense:

```sql
-- Check classification distribution for a tenant
SELECT classification, COUNT(*) as cnt
FROM `sm-neurogum.sm_metadata.dim_tenant_custom_objects`
GROUP BY 1;
```

Expected classifications:
- `tenant_dataset_custom` - Objects in tenant-created datasets (e.g., `customized_views`)
- `tenant_or_legacy_in_standard_dataset` - Custom objects in SM datasets
- `sm_owned_nondefault` - SM objects not in standard model set
- `oob_v2` - Out-of-box v2 models (should NOT be in docs)

## Key Files to Review

| File | Purpose |
|------|---------|
| `macros/distro/mdw/utils/generate_dim_tenant_custom_objects.sql` | Source data generation |
| `mintlify/tenants/README.md` | Documentation structure |
| `mintlify/tenants/neurogum/custom-objects.mdx` | Example with manual enhancements |
| `mintlify/tenants/zbiotics/custom-objects.mdx` | Complex multi-dataset example |

## Questions for Reviewer

1. Should we add more context to the index pages (e.g., tenant-specific notes)?
2. Is the "low usage" warning threshold appropriate (objects with <100 queries in 180d)?
3. Should we include DDL for all objects or just top objects?
4. Do we need a way to exclude certain datasets from documentation (e.g., `dbt_*` developer datasets)?

## Rollback Plan

If issues arise after merge:
1. Revert the `mintlify/tenants/` directory
2. Pages will 404 (no navigation links to break)
3. No impact on public documentation
