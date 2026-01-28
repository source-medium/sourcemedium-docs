# Query Library (AI Analyst) — Spec (Codex)

Status: In progress (Batches 1–5 shipped)  
Owner: Docs (Data Activation) + AI Analyst  
Last updated: 2026-01-28

## Background

We want a **high-quality, highly relevant query library** that:

1) Improves the AI Analyst’s SQL generation (better patterns + fewer mistakes).  
2) Improves customer self-serve docs (“how to query SourceMedium tables”).  
3) Creates a testable, versioned set of “gold” SQL templates we can QA/validate in batches.

We already have three strong sources of truth:

- **Uni2 SQL rules** (authoritative): `src/agent_core/agents/prompts.py` + `src/agent_core/domain_tables.py`.  
- **QA patterns + SQL guidelines** (useful but secondary when conflicting): `uni-training/.claude/shared/*`.  
- **Eval dataset + artifacts** (seed set): `uni-training/eval3.json` (120 Qs) plus pre-generated SQL artifacts under `uni-training/questions_grouped/unique/Q*/artifacts/generated-queries.sql` (and sometimes `generated-queries_revised.sql`).

Important conflict resolution rule:
- If `uni-training/.claude` guidance conflicts with **uni2** logic, **prefer uni2**.

Note on datasets:
- `uni-training/eval3.json` is the primary seed for v0 because it maps cleanly to the `questions_grouped/unique/Q*/` artifact folders.
- `uni-training/evaluation/training_simplified.json` is a useful supplemental pool, but not the v0 extraction source.

## Goals

- Establish a **repeatable batching workflow** (5–10 queries per batch) to: prioritize → normalize → QA → validate → publish.
- Build an initial “gold” set focused on **core tables** and **high-frequency questions** (revenue/orders/AOV, products, new vs repeat, basic marketing/ad performance, cohorts).
- Ensure every published query is:
  - safe to copy/paste (uses placeholders like `your_project.sm_transformed_v2.<table>`),
  - schema-correct (columns exist),
  - aligned with uni2 business logic conventions (filters, attribution semantics, channel semantics).

## Non-goals (for v0)

- Exhaustive coverage of every table and edge-case.
- Complex multi-touch/MTA journey analysis (only include when explicit intent; later batches).
- Highly tenant-specific enumerations (UTM/campaign value lists) embedded directly in docs.

## Guiding Principles (Hard Requirements)

### SQL correctness + safety

- **No invented columns**: only reference documented columns for the table.
- **Always use valid-order filters** on order tables:
  - `WHERE is_order_sm_valid = TRUE` (and only use `order_cancelled_at` when it exists on the selected table).
- **No LIKE/REGEXP on low-cardinality categorical columns** (uni2 rule):
  - For dimensions like `sm_channel`, `source_system`, `sm_utm_source`, `sm_utm_medium`, `sm_utm_source_medium`, etc. use `=` / `IN` with normalized comparisons (e.g., `LOWER(TRIM(col)) = 'meta'`).
  - If the query needs “contains”-style matching, prefer a **discovery-first** step that enumerates actual values, then exact-match in the final query.
- **Assumptions header** at top of every “gold” query:
  - `-- Assumptions: timeframe=<...> | metric=<...> | grain=<...> | scope=<...>`
- **Channel semantics must be correct** (uni2 rule):
  - `source_system` = system/platform of origin (ads platform vs commerce platform depends on table domain).
  - `sm_channel` = normalized sales channel (`online_dtc`, `amazon`, `tiktok_shop`, etc.). Do not substitute one for the other.
- **Default timeframe**:
  - If query is an operational metric and the question lacks a timeframe, default to **last 30 days**.

### Docs compatibility

- SQL in docs should use:
  - `your_project.sm_transformed_v2.<table>` (and `your_project.sm_experimental.<table>` only for explicitly experimental/MTA examples).
- Keep examples compact and scannable:
  - Prefer “one query per example” (or a clearly labeled 2-step pattern when discovery is required).

## Where the Query Library Lives (Docs)

We publish in two places (single source of truth + pointer):

1) **SQL Query Library (canonical, BigQuery-facing)**
   - Location: `sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`
   - This is the canonical home for copy/paste SQL templates.

2) **AI Analyst Query Library pointer (AI Analyst-facing)**
   - Location: `sourcemedium-docs/ai-analyst/query-library/index.mdx`
   - Purpose: link AI Analyst users to the canonical SQL Query Library page.

3) **Per-table “Example Queries” sections** (table-oriented, schema-first; follow-up)
   - Add a small curated set (2–5) to high-traffic tables under:
     - `sourcemedium-docs/data-activation/data-tables/sm_transformed_v2/*.mdx`
   - Start with:
     - `obt_orders`, `dim_orders`, `obt_order_lines`, `rpt_executive_summary_daily`, `rpt_ad_performance_daily`, `rpt_cohort_ltv_*`, `rpt_outbound_message_performance_daily`, `obt_funnel_event_history`.

Navigation note (v0):
- We added a redirect from the old permalink `/data-activation/template-resources/sm-sql-recipe-directory` → `/data-activation/template-resources/sql-query-library` in `sourcemedium-docs/docs.json`.

## Current Progress

### Batch 1 (shipped to docs)
- Canonical page: `sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`
- AI Analyst pointer: `sourcemedium-docs/ai-analyst/query-library/index.mdx`
- Batch 1 queries included: Q011, Q001, Q022, Q021, Q003, Q119, Q060, Q023
- Validation status:
  - Static schema/column validation: done (docs validator).
  - Live BigQuery dry-run validation (`bq query --dry_run ...`): pending engineering gate.

### Batch 2 (shipped to docs; pending dry-run gate)
- Canonical page: `sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`
- Batch 2 queries added: Q081, Q082, Q083, Q017, Q062, Q115
- Why these queries (selection rationale):
  - **High-frequency questions** we repeatedly see (ROAS trend, acquisition trend, top products, refunds, channel mix, new-customer product mix).
  - **Core, stable tables** only (`sm_transformed_v2`): `rpt_ad_performance_daily`, `rpt_executive_summary_daily`, `obt_orders`, `obt_order_lines`.
  - **Low QA risk**: minimal joins, clear grains, and metrics align with uni2 routing rules (platform ROAS from ad performance tables; unique new customers from executive summary; last-click marketing channel from `sm_utm_source_medium`).
  - **Complements Batch 1** by adding time-series + refunds + channel-mix + “new customer product” patterns without introducing MTA/experimental tables.
  - Validation status:
    - Static schema/column validation: done (0 issues for the canonical page’s SQL blocks).
    - Live BigQuery dry-run validation (`bq query --dry_run ...`): pending engineering gate.

### Batch 3 (shipped to docs; validated 2026-01-27)
- Canonical page: `sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`
- Batch 3 queries added (stumper templates): Q029, Q041, Q019, Q007, Q018
- Also includes Product Insights section with recursive CTE product combinations query.
- Why these queries:
  - They force the most common "gotchas": cohort denominators, first-valid-order anchoring, and choosing cohort-table vs dynamic LTV.
  - They reuse canonical, documented tables (`sm_transformed_v2`) and keep logic explicit (no implicit "subscription" inference via LIKE).
  - They're the patterns most likely to improve analyst self-serve and reduce AI Analyst failure modes on LTV/retention.
- Validation status:
  - Live BigQuery execution validation: **done** (2026-01-27, `sm-irestore4`)
  - Batch 3 SQL templates executed successfully and returned plausible results.
  - Issue found and fixed: Product Combinations query was missing `sku IS NOT NULL` and product-title exclusion filter, causing "Order Specific Details - Not a Product" to pollute results. Fixed by adding standard exclusion pattern.

### Batch 4 (shipped to docs; pending dry-run gate)
- Added “Attribution & Data Health (diagnostics)” queries DQ01–DQ06.
- Static schema/column validation: done for the SQL Query Library page (includes `sm_metadata` + `sm_transformed_v2` examples).
- Live BigQuery dry-run validation: pending engineering gate.

### Batch 5 (shipped to docs; pending dry-run gate)
- Added “attribution stumpers” queries DQ07–DQ12 (discovery → trend → segmentation → proxy breakouts).
- Static schema/column validation: done for the SQL Query Library page.
- Live BigQuery dry-run validation: pending engineering gate.

### Batch 6 (planned — advanced retention/LTV stumpers)

Target: common “hard questions” that typically stump people because they require:
- correct first-valid-order cohorting (`sm_valid_order_index = 1`),
- careful time-windowing (30/60/90-day horizons),
- knowing when to use **cohort tables** (CAC + payback) vs **dynamic** order/order-line logic,
- subscription retention/churn **proxies** (behavioral retention, not billing-system churn).

Proposed queries (5–10; likely 7):
1) **Payback period by acquisition source/medium** (cohort table; uses `cost_per_acquisition`)
2) **LTV:CAC ratio by acquisition source/medium** (cohort table; 6m net LTV vs CAC)
3) **Repeat purchase rate (paid orders only) within 30/60/90 days by acquisition source/medium** (dynamic; `obt_orders`, filters repeat orders to `order_net_revenue > 0`)
4) **Repeat purchase rate (paid orders only) within 30/60/90 days by subscription vs one-time first order** (dynamic; `obt_orders`, filters repeat orders to `order_net_revenue > 0`)
5) **90-day LTV by first-order product_type (primary first-order attribute)** (dynamic; `obt_order_lines` + `obt_orders`)
6) **90-day LTV by first-order product_vendor (primary first-order attribute)** (dynamic; `obt_order_lines` + `obt_orders`)
7) **Repeat purchase rate (paid orders only) within 30/60/90 days by first-order AOV bucket** (dynamic; `obt_orders`, filters repeat orders to `order_net_revenue > 0`)

Why these queries:
- They are “stumpers” that drive frequent confusion and AI Analyst failure modes (cohort anchoring + double counting + horizon logic).
- They are broadly reusable templates across brands without tenant-specific enumerations.
- They intentionally exercise the key scalable tables:
  - cohort table for CAC/payback (`rpt_cohort_ltv_by_first_valid_purchase_attribute_no_product_filters`)
  - order-level analysis (`obt_orders`)
  - product attribute analysis at scale (`obt_order_lines`)

## Query Entry Format (Canonical Metadata)

Each query should have consistent metadata so it can be searched, deduped, and QA’d.

Phased approach (avoid upfront overhead):

### v0 (Batches 1–2): minimal required fields
- `id`: stable identifier (we can start with eval IDs like `Q011` and later alias to `QL-*` if needed)
- `title`
- `domain`
- `primary_table`
- `sql` (docs-ready placeholders)
- `notes` (only when caveats are important)
- `source_artifacts_path` (e.g., `uni-training/questions_grouped/unique/Q011_.../artifacts/generated-queries.sql`)

### v1+ (Batch 3 onward): add structure once patterns emerge
- `archetype`, `time_grain`, `default_timeframe`, `tags`, `example_questions`, `validation_checks`

## Archetypes (Reusable Building Blocks)

We standardize common shapes to maximize reuse:

- `trend`: metric over time + optional period-over-period (PoP) comparison
- `breakdown`: metric by dimension (`sm_channel`, `source_system`, `sm_store_id`)
- `ranking`: top-N entities (products, campaigns, customers) with thresholds
- `cohort_curve`: retention/LTV over months since acquisition
- `funnel`: session/event funnel steps with conversion rates (when available)
- `diagnostic`: data freshness / attribution health / null-coverage checks
- `exploration`: distinct-value discovery query used before exact matches

## Prioritization (How We Pick the Next Batch)

We prioritize with a scoring rubric per candidate query:

1) **User value / frequency**: how often this comes up (use eval dataset + support intuition)
2) **Template reusability**: can it answer multiple phrasings with small parameter tweaks?
3) **Low QA risk**: minimal joins, stable columns, clear semantics
4) **Docs placement value**: would a customer actually copy/paste this from a table page?

Practical batch selection rule:
- Each batch should cover **2–3 archetypes** and **1–2 primary tables** max.
- First batches should skew heavily toward:
  - `obt_orders` / `dim_orders` / `obt_order_lines`
  - plus one “adjacent” table when needed (e.g., `rpt_executive_summary_daily`).

Seed evidence we already have:
- The `questions_grouped/unique/` set is concentrated in Orders/Order Lines/Order Dims, then CAC/ROAS, then cohort/MTA.
- It includes deprecated `sm_experimental.rpt_mta_models_v4` references; those must not be promoted to “gold”.

## QA + Validation Workflow (Batch-Based)

### Step 0 — Candidate selection
- Pick 5–10 candidates using the rubric.
- Decide publication targets:
  - AI Analyst Query Library domain page(s)
  - Specific table pages (if applicable)

### Step 1 — Normalize to docs conventions
- Prefer extracting directly from the eval artifacts first:
  - `uni-training/questions_grouped/unique/Q*/artifacts/generated-queries.sql`
  - If present, compare with `generated-queries_revised.sql` and choose the best starting point.
- Replace literal project IDs with `your_project`.
- Ensure tables are `sm_transformed_v2` unless explicitly experimental.
- Add assumptions header.
- Ensure `is_order_sm_valid = TRUE` is present where required.
- Remove/avoid deprecated tables (e.g., `sm_experimental.rpt_mta_models_v4`).

### Step 2 — Static validation (CI-friendly)
We can validate without warehouse access:

- **Schema/column validation**:
  - Use existing script: `sourcemedium-docs/scripts/docs_column_accuracy.py` (extend or reuse) to validate SQL blocks reference real columns for referenced tables.
- **Style + rule linting** (new checks; should mirror uni2 constraints):
  - enforce assumptions header
  - ban LIKE/REGEXP on categorical columns (or require a “discovery query” pattern first)
  - enforce dataset naming (`your_project.sm_transformed_v2`)
  - enforce required filters for orders tables (`is_order_sm_valid = TRUE`)

### Step 3 — Live validation (engineer-run gate)
- Run BigQuery dry-run for each query example (per docs repo guidance):
  - `bq query --dry_run --use_legacy_sql=false --project_id=sm-uni "<sql>"`
- When feasible, run the query with a constrained timeframe and `LIMIT` to verify it returns plausible results.

### Step 4 — Human QA checklist
- Semantics:
  - `source_system` vs `sm_channel` usage correct
  - revenue definition consistent (prefer `order_net_revenue` unless explicitly otherwise)
  - time bucket derivations correct (BigQuery GoogleSQL)
- Safety:
  - no invented columns
  - no categorical LIKE/REGEXP
  - required validity filters present
- UX:
  - query answers a real question and is easily adaptable
  - notes mention how to scope by store/channel safely

### Step 5 — Publish
- Add to:
  - domain query library page(s)
  - relevant table pages (“Example Queries” section)
- Keep each page scannable with consistent formatting:
  - “When to use”
  - “SQL”
  - “How to adapt” (optional)
  - “Common pitfalls” (optional)

## Batch 1 Recommendation (Initial “Gold” Set)

Target: high ROI, low risk, core tables, directly extractable from eval artifacts.

Concrete, immediately-actionable candidates (from `questions_grouped/unique/`):

| # | Question | Seed ID | Domain | Archetype | Primary table |
|---|----------|---------|--------|-----------|---------------|
| 1 | What is my average CAC? | Q011 | Marketing & Ads | breakdown | `rpt_executive_summary_daily` |
| 2 | Which platform and campaign type has the highest ROAS? | Q001 | Marketing & Ads | ranking | `rpt_ad_performance_daily` |
| 3 | Which source/mediums are driving repeat purchases? | Q021 | Customers / Retention | breakdown | `obt_orders` |
| 4 | What percentage of our orders are first-time vs repeat? | Q022 | Customers | breakdown | `obt_orders` |
| 5 | How has the ratio of new to repeat customers changed? | Q003 | Customers | trend | `rpt_executive_summary_daily` |
| 6 | What are the top 10 products by net revenue? | Q119 | Products | ranking | `obt_order_lines` |
| 7 | What’s the average order value by marketing channel? | Q060 | Revenue / Attribution | breakdown | `obt_orders` |
| 8 | Let’s define current revenue as last 30 days (and compare) | Q023 | Orders & Revenue | trend | `obt_orders` |

Batch size flexibility:
- Start with 5–8 if we want fast iteration; expand to 10 once the publish + QA loop is smooth.

Expected normalization notes for Batch 1:
- Q021/Q060 involve UTMs / source-medium dimensions; ensure uni2-safe categorical handling (avoid LIKE/REGEXP; consider a discovery-first pattern if needed).

## Batch 2 (shipped)

Target: add time-series + refunds + product discovery patterns with minimal QA risk.

Status: shipped; live BQ validation passed (2026-01-28, `sm-irestore4`).

Candidates shipped as Batch 2:
- Q081 — ROAS trends over time (Marketing & Ads; `rpt_ad_performance_daily`)
- Q082 — customer acquisition trends over time (Customers; `rpt_executive_summary_daily`)
- Q083 — top products by units sold (Products; `obt_order_lines`)
- Q017 — products most common with new customers (Products/Customers; `obt_order_lines` + `sm_valid_order_index = 1`)
- Q062 — refund rate by marketing channel (Refunds/Attribution; `obt_orders` + refund fields)
- Q115 — distribution of orders/revenue by sales channel (Sales channels; `obt_orders`)

Notes (what we changed vs eval artifacts):
- Q081/Q082 eval artifacts referenced non-canonical datasets (`sm_experimental.*`, `sm_views.*`). We rewrote to canonical `sm_transformed_v2` tables that match uni2 routing rules.
- Q062 eval artifact used `sm_channel` for “marketing channel”. We rewrote to use `sm_utm_source_medium` (last-click) per uni2 attribution semantics.

## Batch 3 (shipped — “stumper queries”)

Target: expand coverage to questions that routinely stump analysts because they require:
- first-valid-order anchoring,
- careful cohort definitions / denominators,
- choosing between **precomputed cohort tables** vs **dynamic LTV** from `obt_orders`/`obt_order_lines`,
- subscription retention semantics (customer-level retention proxy, not subscription-billing-system churn).

Status: shipped; live BQ validation passed (2026-01-28, `sm-irestore4`).

Batch size: 5–10, but expect higher QA effort per query.

### Primary candidates (recommended for Batch 3)

1) **LTV by first-purchased SKU / product (dynamic, uses order lines)**
   - Question archetype: “Which initial products create the highest 90‑day LTV?”
   - Table(s): `obt_order_lines` (for SKU/product) + `obt_orders` (for first-order anchor if needed)
   - Key requirements:
     - anchor cohort on first **valid** order (`sm_valid_order_index = 1`)
     - define horizon (30/60/90 days) and compute per customer then aggregate by SKU
     - include sample-size guard (`customers >= 10` or higher)

2) **LTV by first-order attribute (dynamic, uses orders)**
   - Question archetype: “What is 90‑day LTV by acquisition source/medium (or discount code / landing page)?”
   - Table(s): `obt_orders` (preferred when the attribute exists at order level)
   - Key requirements:
     - anchor cohort on first **valid** order (`sm_valid_order_index = 1`)
     - use `order_net_revenue` as default LTV metric unless the question specifies otherwise

3) **Retention % by acquisition source/medium (precomputed cohort table)**
   - Question archetype: “How does 3‑month / 6‑month retention vary by acquisition channel?”
   - Table: `rpt_cohort_ltv_by_first_valid_purchase_attribute_no_product_filters`
   - Key requirements:
     - filter `acquisition_order_filter_dimension = 'source/medium'`
     - **must include** `sm_order_line_type = 'all_orders'` to avoid double counting
     - compute retention as `customer_count / cohort_size` at `months_since_first_order = N`
     - include cohort-size guards (`cohort_size >= 10` minimum; prefer `>= 50` for ranked outputs)

4) **Discount-code cohorts: retention + LTV (precomputed cohort table)**
   - Question archetype: “Which discount codes acquire higher-retention customers?”
   - Table: `rpt_cohort_ltv_by_first_valid_purchase_attribute_no_product_filters`
   - Key requirements:
     - filter `acquisition_order_filter_dimension = 'discount_code'`
     - `sm_order_line_type = 'all_orders'` (no double counting)
     - discovery-first if discount codes are messy (enumerate top codes by cohort_size, then analyze)

5) **Subscription vs one-time: retention + LTV comparison (precomputed cohort table)**
   - Question archetype: “How much more valuable are subscription customers vs one-time?”
   - Table: `rpt_cohort_ltv_by_first_valid_purchase_attribute_no_product_filters`
   - Key requirements:
     - be explicit whether we mean:
       - **first-order type** cohorts (use `acquisition_order_filter_dimension = 'order_type_(sub_vs._one_time)'`), or
       - **lifetime behavior** subsets (use `sm_order_line_type IN ('subscription_orders_only','one_time_orders_only')`)
     - never aggregate across `sm_order_line_type` without filtering (triple-count risk)

### Secondary candidates (pick 0–3 if we want 8–10 in Batch 3)

- Contribution profit trend by channel (`rpt_executive_summary_daily`, time series).
- Payback period proxy (cohort LTV + CAC scalar):
  - Use cohort table for marketing acquisition dimensions; add CAC from `rpt_executive_summary_daily` at matching grain.
- Purchase interval distribution for non-subscribers (orders; window functions, careful filters).

### Reference guidance (useful, but uni2 wins on conflicts)
- Uni2 authoritative routing + rules: `src/agent_core/agents/prompts.py`
- Cohort-table cautions (double-counting; dimensions): `uni-training/.claude/shared/MODEL_KNOWLEDGE.md`

## Batch 4 + 5 (merged, shipped — attribution + data health)

Status: shipped; live BQ validation passed (2026-01-28, `sm-irestore4`).

Target: attribution coverage + data health diagnostics ("why is everything direct / missing?") plus actionable follow-up patterns.

Notes:
- `dim_data_dictionary` lives in `your_project.sm_metadata.dim_data_dictionary` (not `sm_transformed_v2`).
- We removed redundant queries (DQ03/DQ07 source/medium snapshots redundant with DQ06 trend view).
- Fixed click-id coverage query to exclude `'(none)'` placeholder values.
- Removed DQ## prefixes from titles for readability.

Final queries shipped (10 data health queries):
1. Which tables are stale or missing data? (`sm_metadata.dim_data_dictionary`)
2. Attribution column coverage on orders (`sm_metadata.dim_data_dictionary`)
3. When UTMs are missing, what other attribution signals exist? (`obt_orders`)
4. Top referrer domains for orders missing UTMs (`obt_orders`)
5. Key join-key completeness (customers + SKU coverage) (`obt_orders` + `obt_order_lines`)
6. Attribution health trend (weekly) (`obt_orders`)
7. Attribution health by store and sales channel (`obt_orders`)
8. Discount code parsing (top codes by revenue) (`obt_orders`)
9. Top landing pages for orders missing UTMs (`obt_orders`)
10. Click-id coverage vs UTM coverage (gclid/fbclid) (`obt_orders`)

## Handling “Discovery-First” Without Breaking uni2 Rules

Some analyses (especially UTMs) are high-entropy in practice. To stay aligned with uni2’s “no categorical LIKE/REGEXP” rule, doc examples should prefer:

- A small **exploration query** to enumerate actual distinct values (recent window, top by frequency).
- A final query that uses **exact matches / IN** with normalized comparisons.

This also avoids embedding tenant-specific value assumptions in docs.

## Success Metrics (What “Good” Looks Like)

- We can consistently ship 5–10 “gold” queries per batch with low churn.
- Docs examples pass static schema checks and dry-run checks.
- The AI Analyst produces fewer SQL retries / QA failures on the same archetypes.
- Coverage improves against the eval set (e.g., % of eval questions matched to a “gold” archetype).

## Open Questions

1) Source of truth (decision):
   - Canonical “gold” queries live in `sourcemedium-docs/` (these are documentation artifacts). Uni2 can optionally consume them later, but docs should own validation + publication.
2) “Gold” vs “Draft”:
   - Do we publish drafts in docs (clearly marked), or keep drafts internal until validated?
3) MTA sequencing:
   - When do we start including MTA examples (explicit intent only), and how do we label experimental limitations?

## v0 Exit Criteria (Ship Gate)

We consider v0 shipped when:
- ≥ 10 queries are published on the canonical SQL page (`sourcemedium-docs/data-activation/template-resources/sql-query-library.mdx`),
- each new query passes BigQuery dry-run against a real project (`--project_id=sm-uni`) before placeholder rewrite,
- each query has engineering QA sign-off,
- at least 3 core table pages have updated “Example Queries” sections (recommended: `obt_orders`, `dim_orders`, `obt_order_lines`).

## Table Preference (One-liners)

- Prefer `obt_orders` for order-level aggregations where you want the wide “analytics-ready” order fields (revenue/profit/refunds/channel context) with minimal joins.
- Prefer `dim_orders` when you specifically need order sequencing fields like `sm_valid_order_index` for new vs repeat logic and other “dimension” attributes.
