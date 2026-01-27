# Query Library (AI Analyst) — Spec (Codex)

Status: In progress (Batch 1 shipped)  
Owner: TBD (Docs + AI Analyst)  
Last updated: 2026-01-27

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

## Batch 2 (up next)

Target: add time-series + refunds + product discovery patterns with minimal QA risk.

Proposed candidates (from `questions_grouped/unique/`):
- Q081 — ROAS trends over time (Marketing & Ads; `rpt_ad_performance_daily`)
- Q082 — customer acquisition trends over time (Customers; `rpt_executive_summary_daily`)
- Q083 — top products by units sold (Products; `obt_order_lines`)
- Q062 — refund rate by marketing channel (Refunds/Attribution; likely `obt_orders` + refund fields)
- Q115 — distribution of retail vs wholesale vs DTC vs Amazon (Sales channels; `obt_orders`)
- Q017 — products most common with new customers (Products/Customers; `obt_order_lines` + first-order filter)

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
