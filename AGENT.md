# AGENT.md (Codex CLI)

This file provides guidance to Codex CLI when working with the SourceMedium documentation repository.

## Repository Overview

This is a **Mintlify (MDX) documentation site** for SourceMedium, a data analytics platform for e-commerce brands.

Key content areas:
- `onboarding/` (getting started, analytics tooling)
- `data-inputs/` (integrations + configuration sheet docs)
- `data-transformations/` (naming conventions, transformation philosophy)
- `data-activation/` (Managed Data Warehouse, Managed BI modules, data tables)
- `help-center/` (FAQs, core concepts)
- `mta/` (multi-touch attribution)

Primary config:
- `docs.json` (Mintlify navigation + site config)

## Working Style (Codex-specific)

- Prefer **deterministic** checks over guesswork. If you can’t prove a claim from repo sources, soften language or ask for clarification.
- When asked for **audit/feedback only**, do not edit files. When asked to implement, keep diffs minimal and scoped.
- Avoid inventing field names: for table/column accuracy, treat the **dbt codebase + MDW config** as source of truth.
- Do not commit/push unless explicitly asked. When asked, run validations first.

## Essential Commands

```bash
# Local preview (requires Mintlify CLI installed)
mintlify dev

# Basic validation
python3 -m json.tool docs.json

# Find Notion URLs (should be none in published docs)
rg -n "notion\\.so|www\\.notion\\.so|notion\\.site" -S .
```

### Navigation reference validation (docs.json -> files exist)

```bash
python3 << 'PY'
import json, os, sys
def extract_refs(obj, refs):
    if isinstance(obj, str) and not obj.startswith("http"):
        refs.append(obj)
    elif isinstance(obj, list):
        for i in obj: extract_refs(i, refs)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("tabs","pages","navigation","groups"):
                extract_refs(v, refs)
    return refs
refs = extract_refs(json.load(open("docs.json")), [])
missing = [f"{r}.mdx" for r in refs if not os.path.exists(f"{r}.mdx")]
if missing:
    print("Missing (first 10):", missing[:10])
    sys.exit(1)
print(f"OK: {len(refs)} nav refs resolve")
PY
```

## Content Conventions

- Filenames: kebab-case, `.mdx`.
- Frontmatter is required for `.mdx`:
  ```yaml
  ---
  title: "Page Title"
  description: "Short SEO summary"
  # optional: sidebarTitle, icon, route
  ---
  ```
- Internal links: use site routes like `/data-activation/...` (no `.mdx`).
- Directory links: use explicit `/folder/index` paths (Mintlify doesn't auto-resolve `/folder` to `/folder/index.mdx`).

### Mintlify MDX components

Use Mintlify components for consistent formatting:
```mdx
<Info>Informational note</Info>
<Tip>Helpful suggestion</Tip>
<Note>Important callout</Note>
<Warning>Caution or gotcha</Warning>
```

## CI/CD checks (what PRs may fail on)

Workflows validate:
- JSON validity (`docs.json`)
- spelling (codespell)
- link checking (lychee)
- navigation references resolve to files

If spellcheck flags domain terms, add them to the workflow ignore list (don’t “misspell” product names).

## Notion Policy

- Do not leave Notion pages “floating around” as canonical docs.
- Remove/replace links to Notion URLs (`notion.so`, `notion.site`) in published content.
- When migrating content from Notion, convert to `.mdx`, add frontmatter, and ensure the page is reachable via `docs.json`.

## Data Table Documentation (`sm_transformed_v2`)

Table docs live in:
- `data-activation/data-tables/sm_transformed_v2/*.mdx`

These pages include a fenced YAML block that should mirror customer-facing schema.

### Customer-facing dataset

- Prefer examples using `your_project.sm_transformed_v2.<table>` (customer-facing).
- Avoid legacy/internal dataset names like `masterset` in examples.

### Source of truth for column names

In the **monorepo** (common in this workspace), the dbt project lives adjacent to this docs repo.
Use it to verify schema accuracy:
- `../dbt_project.yml`
- `../models/**`

Key config:
- Rename map: `vars.mdw_schema_config.rename_column_map_all`
- Exclusions: `vars.mdw_schema_config.excluded_columns_all_tables`

Interpretation:
- Docs should reflect **post-rename** (customer-facing) column names.
- Do not document excluded columns (even if they exist in dbt YAML).

If the dbt codebase is not available, fall back to:
- `yaml-files/latest-v2-schemas-*.json`
- Warehouse inspection (`bq show --schema ...`) when available

### Struct field documentation

For struct/nested columns, document subfields with dot-notation when they are queryable as separate fields:
```yaml
- name: ad_platform_reported_conversion_windows
  description: Struct containing conversion metrics across windows.

- name: ad_platform_reported_conversion_windows.default_window
  description: Platform default conversions window.
```

### Common pitfalls (high frequency)

- Documenting excluded columns (e.g., columns listed in `excluded_columns_all_tables`)
- Documenting pre-rename names (e.g., `smcid` instead of `sm_store_id`)
- Directory links without `/index` suffix (use `/folder/index`, not `/folder`)
- dbt YAML includes columns that may not be present in exported MDW schema (verify against config + warehouse when possible)
- **Config vs production mismatch**: `dbt_project.yml` may show display labels (e.g., `'1st Order'`) but actual data uses different values (e.g., `'1st_order'`). Always verify against production data.

## Navigation Restructure Guidelines

When reorganizing `docs.json` navigation:

### Safe Approach: Nav-Only Refactor
1. **Change only `docs.json`** - Don't move files in the first pass
2. **Run validation after every change** - `python3 -m json.tool docs.json` + nav ref check
3. **Audit for orphan pages** - Compare files on disk vs pages in navigation

### Orphan Page Detection
After restructuring, verify no pages were dropped:
```bash
# Find .mdx files not in docs.json (potential orphans)
comm -23 <(find . -name "*.mdx" -not -path "./snippets/*" | sed 's|^\./||;s|\.mdx$||' | sort) \
         <(python3 -c "import json; exec('''
def extract(obj, refs):
    if isinstance(obj, str) and not obj.startswith(\"http\"): refs.append(obj)
    elif isinstance(obj, list): [extract(i, refs) for i in obj]
    elif isinstance(obj, dict): [extract(v, refs) for k,v in obj.items() if k in (\"tabs\",\"pages\",\"navigation\",\"groups\")]
    return refs
print(\"\\n\".join(sorted(extract(json.load(open(\"docs.json\")), []))))
''')" | sort)
```

### URL Verification
**Never hallucinate URLs** - Always derive URLs from actual file paths:
- File: `help-center/faq/data-faqs/why-dont-new-customers-match.mdx`
- URL: `https://docs.sourcemedium.com/help-center/faq/data-faqs/why-dont-new-customers-match`

The validation script checks file existence, NOT URL correctness. When opening pages for QA, copy paths from `docs.json` or file listings.

### Recommended deterministic audit (monorepo)

If `../dbt_project.yml` exists, compare docs table YAML blocks against dbt YAML columns,
applying `rename_column_map_all` and excluding `excluded_columns_all_tables`.
(Keep this check as a gate for "schema accuracy" work.)

### Verifying Enum Values Against Production

**CRITICAL:** Config files may show display labels that differ from actual data values. Always verify enum values against production data:

```sql
-- Verify actual values in sm-democo warehouse
SELECT DISTINCT order_sequence FROM `sm-democo.sm_transformed_v2.obt_orders` WHERE order_sequence IS NOT NULL
-- Returns: 1st_order, repeat_order (NOT 'First Order', 'Repeat Order')

SELECT DISTINCT subscription_order_sequence FROM `sm-democo.sm_transformed_v2.obt_orders` WHERE subscription_order_sequence IS NOT NULL
-- Returns: 1st_sub_order, recurring_sub_order, one_time_order
```

**Pattern:** Config files describe intended display values; actual implementation uses snake_case constants.

### Handling Orphaned Files During Consolidation

When consolidating docs, don't delete old files immediately:
1. Add redirect `<Info>` notice pointing to new location
2. Keep in place for one release cycle (allows external links to still work)
3. Delete in follow-up PR after confirming no broken external references

Example redirect notice:
```mdx
<Info>
This page has moved to [New Location](/path/to/new-page). Please update your bookmarks.
</Info>
```

## When you’re unsure

- Prefer asking a targeted question over writing speculative content.
- For external platform defaults/claims (Meta/Google/TikTok attribution windows, etc.), only state specifics if:
  - they’re documented in-repo, or
  - you add explicit caveats (“varies by account settings; confirm in platform UI”).

