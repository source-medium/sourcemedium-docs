# CLAUDE.md

This file provides guidance to Claude Code when working with the SourceMedium documentation repository.

## Project Overview

This is a **Mintlify documentation site** for SourceMedium, a data analytics platform for e-commerce brands. The docs cover:
- Platform integrations (Shopify, Meta, Google Ads, Klaviyo, etc.)
- Data transformation and activation
- Dashboard/BI usage guides
- Attribution and analytics concepts

**Tech Stack:** Mintlify (MDX-based docs framework), GitHub Actions for CI/CD

## Essential Commands

```bash
# Local development
mintlify dev                    # Start local dev server (requires npm install -g mintlify)

# Validation (run before committing)
python3 -m json.tool docs.json  # Validate JSON syntax

# Navigation validation script (from CI workflow)
python3 << 'EOF'
import json, os, sys
def extract_refs(obj, refs=[]):
    if isinstance(obj, str) and not obj.startswith('http'): refs.append(obj)
    elif isinstance(obj, list): [extract_refs(i, refs) for i in obj]
    elif isinstance(obj, dict): [extract_refs(v, refs) for k,v in obj.items() if k in ('tabs','pages','navigation','groups')]
    return refs
refs = extract_refs(json.load(open('docs.json')))
missing = [f"{r}.mdx" for r in refs if not os.path.exists(f"{r}.mdx")]
if missing: print(f"Missing: {missing[:10]}"); sys.exit(1)
print(f"✅ All {len(refs)} nav refs valid")
EOF
```

## Directory Structure

```
sourcemedium-docs/
├── docs.json                 # Main navigation config (Mintlify)
├── help-center/              # FAQs, guides, troubleshooting
│   ├── faq/
│   │   ├── account-management-faqs/
│   │   ├── dashboard-functionality-faqs/
│   │   ├── data-faqs/
│   │   └── configuration-sheet-faqs/
│   └── core-concepts/
├── data-inputs/              # Integration guides
│   ├── platform-integration-instructions/   # Setup guides per platform
│   ├── platform-supporting-resources/       # Platform-specific deep dives
│   ├── configuration-sheet/                 # Config sheet docs
│   └── attribution-health/                  # Attribution improvement guides
├── data-transformations/     # How SM transforms data
│   └── naming-conventions/   # Column/table naming standards
├── data-activation/          # Using SM data
│   ├── managed-data-warehouse/
│   ├── managed-bi-v1/modules/
│   ├── data-tables/          # Table documentation
│   └── template-resources/   # Looker Studio templates
├── onboarding/               # Getting started content
│   ├── getting-started/
│   └── analytics-tools/
├── mta/                      # Multi-Touch Attribution docs
├── snippets/                 # Reusable MDX snippets
├── images/                   # All images (article-imgs/, platform-logos/)
└── .github/workflows/        # CI/CD (docs-quality.yml)
```

## docs.json Navigation Structure

The navigation uses a `tabs > groups > pages` hierarchy:

```json
{
  "navigation": {
    "tabs": [
      {
        "tab": "Tab Name",
        "groups": [
          {
            "group": "Group Name",
            "pages": [
              "path/to/page",           // Simple page reference
              {                          // Nested group
                "group": "Nested Group",
                "pages": ["path/to/nested-page"]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Current Tabs:**
- Overview (getting started, core concepts)
- Connect Your Data (integrations, configuration)
- Understand Your Data (transformations, attribution)
- Use Your Data (MDW, dashboards, data tables)
- Reference (metrics, dimensions, data dictionary)
- Help (FAQs, troubleshooting)
- MTA (multi-touch attribution)

**Important:** Page references are paths WITHOUT `.mdx` extension. They must match actual file paths.

## MDX Components

Mintlify provides these components (use them for consistent formatting):

### Callouts
```mdx
<Info>Informational note</Info>
<Tip>Helpful suggestion</Tip>
<Note>Important callout</Note>
<Warning>Caution or gotcha</Warning>
```

### Cards & Groups
```mdx
<CardGroup cols={2}>
  <Card title="Card Title" icon="icon-name" href="/path/to/page">
    Card description
  </Card>
</CardGroup>
```

### Tabs
```mdx
<Tabs>
  <Tab title="First Tab">Content for first tab</Tab>
  <Tab title="Second Tab">Content for second tab</Tab>
</Tabs>
```

### Accordions
```mdx
<Accordion title="Expandable Section">
  Hidden content revealed on click
</Accordion>

<AccordionGroup>
  <Accordion title="Item 1">Content 1</Accordion>
  <Accordion title="Item 2">Content 2</Accordion>
</AccordionGroup>
```

### Steps
```mdx
<Steps>
  <Step title="Step 1">First step content</Step>
  <Step title="Step 2">Second step content</Step>
</Steps>
```

### Tooltips & Snippets
```mdx
<Tooltip tip="Explanation text">Term</Tooltip>

{/* Include reusable snippet */}
<Snippet file="snippet-name.mdx" />
```

## Frontmatter

Every `.mdx` file needs frontmatter:

```yaml
---
title: "Page Title"                    # Required
sidebarTitle: "Short Nav Title"        # Optional - shorter title for sidebar
description: "SEO description"         # Optional but recommended
icon: 'icon-name'                      # Optional - Font Awesome icon
---
```

Common icons: `plug`, `chart-line`, `question-mark`, `book`, `gear`, `heart-pulse`, `tags`

## CI/CD Quality Checks

PRs trigger `.github/workflows/mintlify-docs-update.yml` which validates:

1. **JSON Validation** - Ensures docs.json is valid
2. **Navigation Validation** - All page refs point to existing files
3. **Mintlify Validation** - Runs `mintlify validate` (non-blocking due to pre-existing MDX issues)

**Note:** Mintlify auto-deploys on merge to master. The CI workflow is validation-only—no build/deploy steps needed.

**Ignored terms** (add to workflow if needed): smcid, sourcemedium, hdyhau, utm, cogs, ltv, roas, aov, klaviyo, shopify, etc.

## Writing Guidelines

### Terminology
- **SMCID** - SourceMedium Customer ID (unique identifier)
- **HDYHAU** - "How Did You Hear About Us?" (post-purchase survey)
- **MTA** - Multi-Touch Attribution
- **LTV** - Lifetime Value
- **ROAS** - Return on Ad Spend
- **AOV** - Average Order Value
- **Zero-party data** - Customer-provided info (surveys)
- **First-party data** - Tracking-based data (UTMs, GA4)

### Style
- Use sentence case for headings
- Prefer active voice
- Keep paragraphs short (3-4 sentences max)
- Use tables for comparisons and reference info
- Use CardGroups for related links/resources
- Use Tabs for alternative approaches or platform-specific content

### Links
- **Internal:** Use relative paths `/data-inputs/platform-integration-instructions/shopify-integration`
- **External:** Full URLs `https://example.com`
- **Never:** Use old `help.sourcemedium.com` URLs (these are deprecated)

## Common Tasks

### Adding a new integration guide
1. Create file: `data-inputs/platform-integration-instructions/<platform>-integration.mdx`
2. Add to `docs.json` navigation under appropriate group
3. Optionally create supporting resources in `data-inputs/platform-supporting-resources/<platform>/`

### Adding a new FAQ
1. Create file in appropriate `help-center/faq/<category>/` folder
2. Add to `docs.json` under "Help" tab > appropriate FAQ group

### Restructuring Navigation
When reorganizing `docs.json`:
1. **Nav-only first** - Change docs.json without moving files
2. **Validate after each change** - Run JSON + nav ref validation
3. **Check for orphans** - See AGENT.md for orphan detection script
4. **Single location per page** - Each page should appear in exactly one place in nav

### Adding images
1. Place in `images/article-imgs/` (or `platform-logos/` for logos)
2. Reference as `/images/article-imgs/filename.png`

### Creating reusable content
1. Create snippet in `snippets/snippet-name.mdx`
2. Use with `<Snippet file="snippet-name.mdx" />`

## Data Table Documentation (sm_transformed_v2)

The `data-activation/data-tables/sm_transformed_v2/` folder contains schema docs for customer-facing tables. These require special attention to ensure accuracy.

### Customer-Facing Dataset
- **Correct:** `sm_transformed_v2` - This is the dataset customers query
- **Incorrect:** `masterset` - Legacy internal dataset, NOT customer-facing
- All SQL examples in docs should use `your_project.sm_transformed_v2.<table>`

### MDW Column Exclusions
The Managed Data Warehouse (MDW) automatically excludes certain columns. **Never document these in table docs:**

1. **Explicit exclusions** - Listed in `dbt_project.yml` under `vars.mdw.excluded_columns_all_tables`:
   - `sm_order_referrer_source`, `_synced_at`, etc.

2. **Naming convention exclusions** (from MDW macros):
   - Columns ending in `_array` (e.g., `order_tags_array`)
   - Columns starting with `_` (e.g., `_synced_at`)

3. **Column renames** - Check `vars.mdw.rename_column_map_all` for transformed names

### Verifying Against Real Warehouse
Before publishing table docs, verify columns exist in customer MDW:

```bash
# Check actual schema in a customer warehouse
bq show --schema sm-irestore4:sm_transformed_v2.<table_name> | jq -r '.[].name' | sort

# Compare with documented columns
grep "name:" <table>.mdx | sed 's/.*name: //' | sort

# Find differences
comm -23 <(documented) <(actual)  # In docs but not warehouse
```

### Struct Field Documentation
For struct/nested columns, document subfields with dot notation:
```yaml
- name: ad_platform_reported_conversion_windows
  description: Struct containing conversion metrics...

- name: ad_platform_reported_conversion_windows.default_window
  description: Platform-reported conversions using default window...

- name: ad_platform_reported_conversion_windows._7d_click
  description: Platform-reported conversions using 7-day click window...
```

### Common Pitfalls
- **dbt YAML ≠ MDW schema** - Columns can be documented in dbt but not implemented in SQL
- **Array columns** - Always excluded from MDW, never document them
- **Duplicate entries** - Watch for accidentally documenting same column twice
- **Directory links** - Use `/folder/index` explicitly (Mintlify doesn't auto-resolve `/folder` to `/folder/index.mdx`)

### Verifying Enum Values
**CRITICAL:** Config files (`dbt_project.yml`) may show display labels that differ from actual data values. Always verify enum values against production data:

```sql
-- Verify actual values in sm-democo warehouse
SELECT DISTINCT order_sequence FROM `sm-democo.sm_transformed_v2.obt_orders` WHERE order_sequence IS NOT NULL
-- Returns: 1st_order, repeat_order (NOT 'First Order', 'Repeat Order')

SELECT DISTINCT subscription_order_sequence FROM `sm-democo.sm_transformed_v2.obt_orders` WHERE subscription_order_sequence IS NOT NULL
-- Returns: 1st_sub_order, recurring_sub_order, one_time_order
```

**Pattern:** Config files describe intended display values; actual implementation uses snake_case constants. Query production data, not config files.

## SQL Examples in Documentation

### Validation Requirement
**All SQL examples MUST be validated by an engineer before merging.** Run queries against a test warehouse (e.g., `sm-democo`) using BigQuery dry-run to catch syntax and schema errors:

```bash
bq query --dry_run --use_legacy_sql=false "SELECT ... FROM \`sm-democo.sm_transformed_v2.obt_orders\` ..."
```

### Query Standards
1. **Required filters for order tables:**
   ```sql
   WHERE is_order_sm_valid = TRUE
   ```

2. **Dataset paths:** Use placeholder format for customer docs:
   ```sql
   FROM `your_project.sm_transformed_v2.obt_orders`      -- Standard tables
   FROM `your_project.sm_experimental.obt_purchase_journeys_with_mta_models`  -- MTA tables
   ```

3. **Placeholders:** Use `your_project` and `your-sm_store_id` consistently (not `{{account_id}}` or `smcid`)

4. **Safe division:** Always use `SAFE_DIVIDE()` to avoid division-by-zero errors

5. **Date/timestamp handling:** BigQuery is strict about types:
   ```sql
   -- Correct: wrap timestamp in DATE() when comparing to DATE
   WHERE DATE(order_processed_at_local_datetime) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)

   -- Wrong: comparing TIMESTAMP to DATE directly
   WHERE order_processed_at_local_datetime >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
   ```

### Common Pitfalls
- **Column `smcid` doesn't exist** → Use `sm_store_id`
- **Column `sm_marketing_channel` doesn't exist** → Use `sm_channel`
- **Reserved word `rows`** → Use `row_count` or another alias
- **Missing required filters** → Order queries need `is_order_sm_valid = TRUE`

## Pre-Commit Validation

Run the validation commands from [Essential Commands](#essential-commands), plus:

```bash
# Test external URLs (spot check key links)
curl -sI "https://support.google.com/looker-studio/" | head -1
# Should return HTTP/2 200
```

### Handling Orphaned Files
When consolidating docs, don't delete old files immediately. Instead:
1. Add redirect `<Info>` notice pointing to new location
2. Keep in place for one release cycle (allows external links to still work)
3. Delete in follow-up PR after confirming no broken external references

## Troubleshooting

### "Page not found" in local dev
- Check file path matches docs.json reference exactly
- Ensure `.mdx` extension exists on file but NOT in docs.json

### CI failing on spell check
- Add legitimate terms to `ignore_words_list` in `.github/workflows/docs-quality.yml`

### CI failing on link check
- Fix broken internal links (check file exists)
- For flaky external links, add to `--exclude` in lychee args

### Navigation not updating
- Ensure valid JSON in docs.json (run `python3 -m json.tool docs.json`)
- Check page path exists as `.mdx` file
