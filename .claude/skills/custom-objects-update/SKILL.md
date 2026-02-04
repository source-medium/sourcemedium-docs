---
name: custom-objects-update
description: Fetch latest custom object data from MDW tenants and update documentation. Run periodically to keep tenant custom objects pages current.
disable-model-invocation: true
allowed-tools: Bash(bq *), Bash(gcloud *), Bash(jq *), Bash(date *), Bash(parallel *), Bash(xargs *), Read, Write, Glob, Grep
---

# Custom Objects Documentation Update

Update tenant custom objects documentation by fetching the latest data from each tenant's BigQuery warehouse.

## Prerequisites

Before running, ensure:
1. You have `bq` CLI installed and authenticated
2. Your GCP credentials have access to tenant projects (`sm-{tenant}`)
3. You're in the mintlify documentation directory

Test authentication:
```bash
bq query --use_legacy_sql=false "SELECT 1"
```

## Arguments

- No arguments: Update all tenants (full refresh)
- `{tenant_id}`: Update only that specific tenant
- `--dry-run`: Preview changes without writing files
- `--list`: List discovered tenants only, no updates
- `--discover`: Check for new tenants not yet documented

## Workflow

### Step 1: Discover ALL Tenants (Including New Ones)

**Primary source:** Query MDW active tenants from dbt_project.yml config via BigQuery metadata.

Run this discovery query to find all tenants with `dim_tenant_custom_objects` tables:

```bash
# Get list of active MDW tenant projects by checking which have the metadata table
bq query --use_legacy_sql=false --format=json "
SELECT
  REPLACE(schema_name, 'sm-', '') as tenant_id
FROM \`region-us\`.INFORMATION_SCHEMA.SCHEMATA_OPTIONS
WHERE option_name = 'default_table_expiration_days'
  AND schema_name LIKE 'sm-%'
LIMIT 100
" 2>/dev/null || echo "[]"
```

**Fallback approach:** Check each known project directly:

```bash
# Known MDW tenant IDs (from dbt_project.yml mdw_config.active_master_account_ids.v2)
KNOWN_TENANTS=(
  avenuez fluencyfirm catalina-crunch theperfectjean irestore-4
  cpap neurogum zbiotics peoplebrandco guardian-bikes xcvi
  elix-healing piquetea catchco lmnt pillar3cx lectronfuelsystems
  upwrd kindpatches idyl
)

# For each, check if dim_tenant_custom_objects exists
for tenant in "${KNOWN_TENANTS[@]}"; do
  # Convert dashes to clean ID (some IDs have dashes, projects use them as-is)
  project="sm-${tenant}"
  if bq query --use_legacy_sql=false "SELECT 1 FROM \`${project}.sm_metadata.INFORMATION_SCHEMA.TABLES\` WHERE table_name = 'dim_tenant_custom_objects' LIMIT 1" &>/dev/null; then
    echo "$tenant"
  fi
done
```

**Also scan existing docs:**
```bash
ls tenants/*.mdx 2>/dev/null | xargs -I{} basename {} .mdx | grep -v README | sort
```

**Compare and identify:**
- Tenants with docs but no BQ data → Mark as potentially churned
- Tenants with BQ data but no docs → **Auto-scaffold new docs**

### Step 2: Auto-Scaffold Missing Tenant Documentation

For any tenant discovered in BigQuery but missing documentation, create both files:

**Create overview page** (`tenants/{tenant_id}.mdx`):

```mdx
---
title: "{Display Name}"
sidebarTitle: "{Display Name}"
description: "Tenant documentation for {Display Name}"
icon: "building"
---

<Info>
This page is not publicly listed and is accessible only via direct URL.
</Info>

## Quick Access

<CardGroup cols={2}>
  <Card title="BigQuery Console" icon="database" href="https://console.cloud.google.com/bigquery?project=sm-{tenant_id}">
    Access your data warehouse directly
  </Card>
  <Card title="Custom Objects" icon="table" href="/tenants/{tenant_id}/custom-objects">
    View tenant-specific tables and views
  </Card>
  <Card title="Standard Tables" icon="chart-line" href="/data-activation/data-tables/sm_transformed_v2">
    Explore SourceMedium data models
  </Card>
  <Card title="Onboarding Guide" icon="rocket" href="/onboarding/getting-started">
    Get started with SourceMedium
  </Card>
</CardGroup>

## Resources

<CardGroup cols={2}>
  <Card title="Configuration Sheet" icon="gear" href="https://docs.google.com/spreadsheets/d/your-config-sheet">
    Manage your data configuration
  </Card>
  <Card title="Dashboard Guide" icon="chart-line" href="/data-activation/managed-bi-v1/modules">
    Learn to use your dashboards
  </Card>
  <Card title="Attribution Health" icon="heart-pulse" href="/data-inputs/attribution-health">
    Improve your attribution data
  </Card>
  <Card title="Help Center" icon="question" href="/help-center">
    FAQs and troubleshooting
  </Card>
</CardGroup>

## Your Data Warehouse

| Property | Value |
|----------|-------|
| Project ID | `sm-{tenant_id}` |
| Standard Dataset | `sm_transformed_v2` |
| Tenant ID | `{tenant_id}` |
```

**Create directory and custom-objects page:**
```bash
mkdir -p tenants/{tenant_id}
```

Then proceed with normal custom objects generation.

### Step 3: Fetch Custom Objects Data (Parallel Execution)

Run queries in parallel for all tenants (max 5 concurrent to avoid rate limits):

```bash
# Create temp directory for results
TMPDIR=$(mktemp -d)

# Function to fetch single tenant
fetch_tenant() {
  local tenant_id="$1"
  local outfile="$TMPDIR/${tenant_id}.json"

  bq query --use_legacy_sql=false --format=json --max_rows=1000 "
  WITH latest_snapshot AS (
    SELECT *,
      ROW_NUMBER() OVER (
        PARTITION BY dataset_id, object_name
        ORDER BY snapshot_at DESC
      ) as rn
    FROM \`sm-${tenant_id}.sm_metadata.dim_tenant_custom_objects\`
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
  " > "$outfile" 2>/dev/null

  if [ $? -eq 0 ]; then
    echo "OK:${tenant_id}"
  else
    echo "FAIL:${tenant_id}"
  fi
}

export -f fetch_tenant
export TMPDIR

# Run in parallel (5 at a time)
echo "${TENANT_LIST[@]}" | tr ' ' '\n' | xargs -P 5 -I{} bash -c 'fetch_tenant "$@"' _ {}
```

### Step 4: Transform Data & Generate Descriptions

For each tenant's JSON results:

1. **Parse and group by dataset_id**
2. **Calculate aggregates:**
   - Object count per dataset
   - Total job_count_180d per dataset
3. **Sort:**
   - Datasets by total jobs (descending)
   - Objects within dataset by job_count (descending)

**Generate LLM-powered descriptions:**

For each object, analyze its name, type, dataset context, and DDL (if available) to generate a meaningful 1-2 sentence description. Consider:

- **Object name patterns:**
  - `orders_*` → Order-related data
  - `*_daily` / `*_hourly` → Time-aggregated metrics
  - `*_summary` → Aggregated summary
  - `obt_*` → "One Big Table" denormalized view
  - `rpt_*` → Report/dashboard data
  - `stg_*` → Staging/intermediate data
  - `dim_*` → Dimension table
  - `fct_*` → Fact table
  - `*_native` → Raw/native data from external source

- **Dataset context:**
  - `customized_views` → Custom views created for this tenant's specific needs
  - `klaviyo` → Email/SMS marketing data from Klaviyo
  - `northbeam_data` → Attribution data from Northbeam
  - `sm_experimental` → Beta/experimental features
  - `sm_transformed_v2` → Customizations to standard models

- **DDL analysis (if available):**
  - Key column names suggest purpose
  - Aggregation patterns (SUM, COUNT, AVG)
  - Join patterns indicate relationships

**Example descriptions:**
- `orders_and_ads_summary` → "Aggregated daily summary joining order metrics with advertising spend data. Key columns: date, sm_channel, new_customers, revenue."
- `dsp_native` → "Raw Amazon DSP (Demand-Side Platform) advertising data. Contains campaign-level spend and performance metrics."
- `rfm_table` → "RFM (Recency, Frequency, Monetary) customer segmentation analysis for targeting and personalization."
- `customer_lifetime_aggregates` → "Lifetime value analysis aggregating customer revenue and acquisition costs by channel."

### Step 5: Generate MDX Content

Generate the custom-objects.mdx file:

```mdx
---
title: "{Display Name} Custom Objects"
sidebarTitle: "Custom Objects"
description: "Inventory of custom BigQuery objects in the {Display Name} data warehouse"
icon: "database"
---

[← Back to {Display Name}](/tenants/{tenant_id}) | [Open sm-{tenant_id} in BigQuery →](https://console.cloud.google.com/bigquery?project=sm-{tenant_id})


# Custom Objects Inventory

This page documents active custom BigQuery tables and views (those queried at least once in the past 180 days) created specifically for {Display Name}, separate from the standard SourceMedium data models.

<Info>
**Last Updated (snapshot_at):** `{snapshot_timestamp} EST`
**Data Source:** Auto-generated from `sm_metadata.dim_tenant_custom_objects`. Only objects with at least 1 query in the past 180 days are included.
</Info>

## Summary

| Dataset | Object Count | Total Jobs (180d) |
|---------|--------------|-------------------|
| [`{dataset_name}`](https://console.cloud.google.com/bigquery?project=sm-{tenant_id}&ws=!1m4!1m3!3m2!1ssm-{tenant_id}!2s{dataset_name}) | {count} | {total_jobs:,} |

---

## Objects by Dataset

### {dataset_name}

<Accordion title="{object_name}">
**Type:** {object_type} | **Queries (180d):** {job_count:,}

{llm_generated_description}

[Open in BigQuery Console →](https://console.cloud.google.com/bigquery?project=sm-{tenant_id}&ws=!1m5!1m4!4m3!1ssm-{tenant_id}!2s{dataset_name}!3s{object_name})

```sql
-- Preview data
SELECT * FROM `sm-{tenant_id}.{dataset_name}.{object_name}` LIMIT 10;
```
</Accordion>

---

## Your Data Warehouse

| Property | Value |
|----------|-------|
| Project ID | `sm-{tenant_id}` |
| Standard Dataset | `sm_transformed_v2` |
| Tenant ID | `{tenant_id}` |

<Info>
For questions about this documentation, contact your SourceMedium team.
</Info>
```

### Step 6: Tenant ID to Display Name Mapping

| Tenant ID | Display Name |
|-----------|--------------|
| `avenuez` | Avenue Z |
| `catalinacrunch` | Catalina Crunch |
| `catalina-crunch` | Catalina Crunch |
| `catchco` | Catch Co |
| `cpap` | CPAP |
| `elix-healing` | Elix Healing |
| `elixhealing` | Elix Healing |
| `fluencyfirm` | Fluency Firm |
| `guardian-bikes` | Guardian Bikes |
| `guardianbikes` | Guardian Bikes |
| `idyl` | Idyl |
| `idylus` | Idyl |
| `irestore-4` | iRestore |
| `irestore4` | iRestore |
| `kindpatches` | Kind Patches |
| `lectronfuelsystems` | Lectron Fuel Systems |
| `lectron-fuel-systems1` | Lectron Fuel Systems |
| `lmnt` | LMNT |
| `neurogum` | Neuro Gum |
| `peoplebrandco` | People Brand Co |
| `pillar3cx` | Pillar 3CX |
| `piquetea` | Pique Tea |
| `theperfectjean` | The Perfect Jean |
| `upwrd` | Upwrd |
| `xcvi` | XCVI |
| `zbiotics` | ZBiotics |

**Fallback:** If tenant ID not in mapping:
1. Check existing `{tenant_id}.mdx` frontmatter for `title` field
2. Otherwise, title-case the ID (replace `-` with space, capitalize words)

### Step 7: Write Files

For each tenant:
```bash
mkdir -p tenants/{tenant_id}
# Write custom-objects.mdx
# Write overview {tenant_id}.mdx if it doesn't exist (auto-scaffold)
```

### Step 8: Update README.md

Update `tenants/README.md` "Current Tenants" table with new object counts.

Parse existing README, update the table rows, preserve other content.

### Step 9: Report Summary and Wait for Confirmation

After processing all tenants, provide a detailed summary:

```markdown
## Custom Objects Update Summary

**Run completed at:** {timestamp}
**Tenants processed:** {count}

### Results by Tenant

| Tenant | Objects | Datasets | Status | Changes |
|--------|---------|----------|--------|---------|
| neurogum | 46 | 5 | ✅ Updated | +2 new, -1 removed |
| zbiotics | 120 | 8 | ✅ Updated | No changes |
| newcustomer | 15 | 2 | 🆕 Scaffolded | New tenant |
| emptyco | 0 | 0 | ⚠️ No objects | - |

### New Tenants Discovered & Scaffolded
- `newcustomer` - Created overview page and custom objects page

### Failed Tenants
| Tenant | Error |
|--------|-------|
| badtenant | Table sm_metadata.dim_tenant_custom_objects not found |

### Files Modified
- `tenants/neurogum/custom-objects.mdx`
- `tenants/zbiotics/custom-objects.mdx`
- `tenants/newcustomer.mdx` (NEW)
- `tenants/newcustomer/custom-objects.mdx` (NEW)
- `tenants/README.md`

### Next Steps
1. Review the changes above
2. Run `mintlify dev` to preview locally (optional)
3. Tell me to commit when ready, or request specific changes
```

**IMPORTANT:** After reporting, wait for user confirmation before any git operations. Do NOT auto-commit.

## Error Handling

| Scenario | Action |
|----------|--------|
| BQ auth failure | Stop immediately, show auth instructions |
| Table doesn't exist for tenant | Skip tenant, include in "Failed" report |
| Empty results (0 objects) | Generate page with notice, include in report |
| Network timeout | Retry once, then skip and report |
| Invalid characters in names | Escape for MDX compatibility |
| Parallel job fails | Collect error, continue with others |

## Dry Run Mode

When `--dry-run` is passed:
1. Perform all queries and transformations
2. Show what files would be created/modified
3. Show diff of changes for existing files
4. Do NOT write any files
5. Report as normal

## Single Tenant Mode

When a specific tenant ID is passed (e.g., `/custom-objects-update neurogum`):
1. Only process that one tenant
2. Skip discovery phase
3. Report only for that tenant
