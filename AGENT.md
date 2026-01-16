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
- Avoid `/.../index` links: Mintlify routes `index.mdx` to the folder path (use `/folder`, not `/folder/index`).

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
- Linking to `/folder/index` instead of `/folder`
- dbt YAML includes columns that may not be present in exported MDW schema (verify against config + warehouse when possible)

### Recommended deterministic audit (monorepo)

If `../dbt_project.yml` exists, compare docs table YAML blocks against dbt YAML columns,
applying `rename_column_map_all` and excluding `excluded_columns_all_tables`.
(Keep this check as a gate for “schema accuracy” work.)

## When you’re unsure

- Prefer asking a targeted question over writing speculative content.
- For external platform defaults/claims (Meta/Google/TikTok attribution windows, etc.), only state specifics if:
  - they’re documented in-repo, or
  - you add explicit caveats (“varies by account settings; confirm in platform UI”).

